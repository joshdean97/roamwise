import hmac

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from core.extensions import db, limiter
from core.mail import send_password_reset_email
from core.models.user import User


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_USERNAME_LENGTH = 80
MAX_EMAIL_LENGTH = 120
RESET_TOKEN_SALT = "roamwise-password-reset-v1"


def normalise_email(value):
    return (value or "").strip().lower()


def _reset_serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt=RESET_TOKEN_SALT,
    )


def generate_password_reset_token(user):
    # Include the current password hash in the signed payload. Once the password
    # changes, every previously-issued reset token automatically becomes invalid.
    return _reset_serializer().dumps({
        "user_id": user.id,
        "email": user.email,
        "password_hash": user.password_hash,
    })


def verify_password_reset_token(token):
    try:
        payload = _reset_serializer().loads(
            token,
            max_age=current_app.config["PASSWORD_RESET_MAX_AGE_SECONDS"],
        )
    except (BadSignature, SignatureExpired):
        return None

    try:
        user_id = int(payload.get("user_id"))
    except (TypeError, ValueError, AttributeError):
        return None

    user = db.session.get(User, user_id)
    if not user:
        return None

    payload_email = payload.get("email") or ""
    payload_password_hash = payload.get("password_hash") or ""

    if not hmac.compare_digest(user.email, payload_email):
        return None

    if not hmac.compare_digest(user.password_hash, payload_password_hash):
        return None

    return user


def _password_error(password, confirm_password):
    if not password or not confirm_password:
        return "Please fill out both password fields."

    if password != confirm_password:
        return "Passwords do not match."

    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."

    if len(password) > MAX_PASSWORD_LENGTH:
        return "Password is too long."

    return None


def _external_reset_url(token):
    path = url_for("auth.reset_password", token=token)
    public_app_url = current_app.config.get("PUBLIC_APP_URL")

    if public_app_url:
        return f"{public_app_url}{path}"

    return url_for("auth.reset_password", token=token, _external=True)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        flash("You are already logged in.", "info")
        return redirect(url_for("main.home"))

    if request.method == "POST":
        email = normalise_email(request.form.get("email"))
        password = request.form.get("password") or ""

        user = (
            User.query
            .filter(func.lower(User.email) == email)
            .first()
        )

        if user and user.check_password(password):
            login_user(user)
            flash("Login successful.", "success")
            return redirect(url_for("main.home"))

        # Deliberately generic: do not reveal whether an email is registered.
        flash("Invalid email or password.", "error")
        return redirect(url_for("auth.login"))

    return render_template("auth/login.html", title="Login")


@auth_bp.route("/logout", methods=["GET","POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        flash("You are already logged in.", "info")
        return redirect(url_for("main.home"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = normalise_email(request.form.get("email"))
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not username or not email or not password or not confirm_password:
            flash("Please fill out all fields.", "error")
            return redirect(url_for("auth.register"))

        if len(username) > MAX_USERNAME_LENGTH:
            flash("Username is too long.", "error")
            return redirect(url_for("auth.register"))

        if len(email) > MAX_EMAIL_LENGTH or "@" not in email:
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("auth.register"))

        password_error = _password_error(password, confirm_password)
        if password_error:
            flash(password_error, "error")
            return redirect(url_for("auth.register"))

        existing_user = User.query.filter(
            (func.lower(User.username) == username.lower())
            | (func.lower(User.email) == email)
        ).first()

        if existing_user:
            flash("Username or email already exists.", "error")
            return redirect(url_for("auth.register"))

        new_user = User(
            username=username,
            email=email,
        )
        new_user.set_password(password)

        try:
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Username or email already exists.", "error")
            return redirect(url_for("auth.register"))

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", title="Register")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        email = normalise_email(request.form.get("email"))

        user = None
        if email and len(email) <= MAX_EMAIL_LENGTH:
            user = (
                User.query
                .filter(func.lower(User.email) == email)
                .first()
            )

        if user:
            token = generate_password_reset_token(user)
            reset_url = _external_reset_url(token)

            try:
                send_password_reset_email(user, reset_url)
            except Exception:
                # Never disclose mail/provider failures to the requester or reveal
                # whether the account exists. The server log remains actionable.
                current_app.logger.exception(
                    "Could not send password reset email for user id %s",
                    user.id,
                )

        flash(
            "If an account exists for that email, we've sent a password reset link.",
            "success",
        )
        return redirect(url_for("auth.forgot_password"))

    return render_template(
        "auth/forgot_password.html",
        title="Forgot password",
    )


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def reset_password(token):
    user = verify_password_reset_token(token)

    if not user:
        flash(
            "That password reset link is invalid or has expired. Request a new one.",
            "error",
        )
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        password_error = _password_error(password, confirm_password)
        if password_error:
            flash(password_error, "error")
            return render_template(
                "auth/reset_password.html",
                title="Reset password",
                token=token,
            )

        user.set_password(password)
        db.session.commit()

        # If the browser happens to have an active session, invalidate it locally
        # too. Other sessions remain subject to Flask-Login's normal session model.
        if current_user.is_authenticated:
            logout_user()

        flash("Password updated. You can log in with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_template(
        "auth/reset_password.html",
        title="Reset password",
        token=token,
    )
