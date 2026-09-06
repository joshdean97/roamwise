import hmac
from datetime import datetime, timezone

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from core.analytics import capture_event
from core.extensions import db, limiter
from core.mail import (
    send_account_deleted_email,
    send_email_confirmation,
    send_password_reset_email,
)
from core.models.user import User


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_USERNAME_LENGTH = 80
MAX_EMAIL_LENGTH = 120
RESET_TOKEN_SALT = "roamwise-password-reset-v1"
EMAIL_CONFIRMATION_TOKEN_SALT = "leaveprints-email-confirmation-v1"
TERMS_VERSION = "2026-09-05"


def normalise_email(value):
    return (value or "").strip().lower()


def _reset_serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt=RESET_TOKEN_SALT,
    )


def _email_confirmation_serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt=EMAIL_CONFIRMATION_TOKEN_SALT,
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


def generate_email_confirmation_token(user):
    return _email_confirmation_serializer().dumps({
        "user_id": user.id,
        "email": user.email,
    })


def verify_email_confirmation_token(token):
    try:
        payload = _email_confirmation_serializer().loads(
            token,
            max_age=current_app.config["EMAIL_CONFIRMATION_MAX_AGE_SECONDS"],
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
    if not hmac.compare_digest(user.email, payload_email):
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


def _public_url(endpoint, **values):
    path = url_for(endpoint, **values)
    public_app_url = current_app.config.get("PUBLIC_APP_URL")

    if public_app_url:
        return f"{public_app_url}{path}"

    return url_for(endpoint, _external=True, **values)


def _send_confirmation_for(user):
    token = generate_email_confirmation_token(user)
    confirmation_url = _public_url("auth.confirm_email", token=token)
    send_email_confirmation(user, confirmation_url)


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
            if not user.is_email_confirmed:
                flash(
                    "Confirm your email before logging in. You can request a new link below.",
                    "info",
                )
                return redirect(url_for("auth.resend_confirmation", email=email))

            login_user(user)
            capture_event("login_completed", user.id)
            flash("Login successful.", "success")
            return redirect(url_for("main.home"))

        # Deliberately generic: do not reveal whether an email is registered.
        flash("Invalid email or password.", "error")
        return redirect(url_for("auth.login"))

    return render_template("auth/login.html", title="Login")


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))


@auth_bp.get("/account")
@login_required
def account():
    return render_template(
        "auth/account.html",
        title="Account | LeavePrints",
    )


@auth_bp.post("/account/change-password")
@login_required
@limiter.limit("10 per hour")
def change_password():
    current_password = request.form.get("current_password") or ""
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("auth.account"))

    password_error = _password_error(password, confirm_password)
    if password_error:
        flash(password_error, "error")
        return redirect(url_for("auth.account"))

    if current_user.check_password(password):
        flash("Choose a new password that is different from your current one.", "error")
        return redirect(url_for("auth.account"))

    user = db.session.get(User, current_user.id)
    user.set_password(password)
    db.session.commit()

    # Match the password-reset flow: sign this browser out after the credential changes.
    logout_user()
    session.clear()
    flash("Password changed. Log in again with your new password.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.post("/account/delete")
@login_required
@limiter.limit("5 per hour")
def delete_account():
    current_password = request.form.get("current_password") or ""
    confirmation = (request.form.get("confirmation") or "").strip()

    if confirmation != "DELETE":
        flash("Type DELETE exactly to confirm permanent account deletion.", "error")
        return redirect(url_for("auth.account"))

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("auth.account"))

    # Do not let an accidental self-delete remove the only admin route back in.
    if current_user.is_admin:
        admin_count = User.query.filter(User.is_admin.is_(True)).count()
        if admin_count <= 1:
            flash(
                "This is the final admin account. Add another admin before deleting it.",
                "error",
            )
            return redirect(url_for("auth.account"))

    from core.analytics import capture_event
    from core.models.analytics_event import AnalyticsEvent
    from core.models.city_data_report import CityDataReport
    from core.models.trip import Trip

    user_id = current_user.id
    user = db.session.get(User, user_id)
    email = user.email
    username = user.username

    try:
        # Reports may contain free text/source links, so delete them rather than
        # merely detaching the user id when the reporter requests erasure.
        CityDataReport.query.filter_by(user_id=user_id).delete(
            synchronize_session=False
        )

        # First-party analytics is intentionally linked only by internal user id.
        # Remove every linked event before recording one anonymous deletion count.
        AnalyticsEvent.query.filter_by(user_id=user_id).delete(
            synchronize_session=False
        )

        # ORM deletion preserves Trip's existing delete-orphan cascades for stops
        # and legs. Removing a trip also kills any public share token immediately.
        for trip in Trip.query.filter_by(user_id=user_id).all():
            db.session.delete(trip)

        db.session.flush()
        db.session.delete(user)
        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Could not delete account for user id %s",
            user_id,
        )
        flash("We couldn't delete your account just now. Please try again.", "error")
        return redirect(url_for("auth.account"))

    logout_user()
    session.clear()

    # Keep only an anonymous product-health count; it cannot be tied back to the
    # deleted account because the user id is deliberately omitted.
    capture_event("account_deleted", None)

    # Deletion must never fail just because the transactional email provider does.
    try:
        send_account_deleted_email(email, username)
    except Exception:
        current_app.logger.exception(
            "Could not send account deletion confirmation to deleted user id %s",
            user_id,
        )

    flash("Your LeavePrints account has been deleted.", "success")
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
        terms_accepted = request.form.get("terms_accepted") == "yes"

        if not username or not email or not password or not confirm_password:
            flash("Please fill out all fields.", "error")
            return redirect(url_for("auth.register"))

        if not terms_accepted:
            flash(
                "Please agree to the Terms of Use and acknowledge the Privacy Policy to create an account.",
                "error",
            )
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
        new_user.terms_accepted_at = datetime.now(timezone.utc)
        new_user.terms_version = TERMS_VERSION

        try:
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Username or email already exists.", "error")
            return redirect(url_for("auth.register"))

        capture_event("account_created", new_user.id)

        try:
            _send_confirmation_for(new_user)
        except Exception:
            current_app.logger.exception(
                "Could not send account confirmation email for user id %s",
                new_user.id,
            )
            flash(
                "Your account was created, but we couldn't send the confirmation email. Try resending it below.",
                "error",
            )
        else:
            flash(
                "Account created. Check your inbox and confirm your email before logging in.",
                "success",
            )

        return redirect(url_for("auth.resend_confirmation", email=email))

    return render_template("auth/register.html", title="Register")


@auth_bp.get("/confirm-email/<token>")
def confirm_email(token):
    user = verify_email_confirmation_token(token)

    if not user:
        flash(
            "That confirmation link is invalid or has expired. Request a new one.",
            "error",
        )
        return redirect(url_for("auth.resend_confirmation"))

    if user.is_email_confirmed:
        flash("Your email is already confirmed. You can log in.", "info")
        return redirect(url_for("auth.login"))

    user.email_confirmed_at = datetime.now(timezone.utc)
    db.session.commit()
    capture_event("email_confirmed", user.id)

    flash("Email confirmed. Welcome to LeavePrints — you can log in now.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/resend-confirmation", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def resend_confirmation():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    email_value = normalise_email(request.args.get("email"))

    if request.method == "POST":
        email = normalise_email(request.form.get("email"))

        user = None
        if email and len(email) <= MAX_EMAIL_LENGTH:
            user = (
                User.query
                .filter(func.lower(User.email) == email)
                .first()
            )

        if user and not user.is_email_confirmed:
            try:
                _send_confirmation_for(user)
            except Exception:
                current_app.logger.exception(
                    "Could not resend account confirmation email for user id %s",
                    user.id,
                )

        # Deliberately generic so this endpoint cannot be used to enumerate users.
        flash(
            "If that address belongs to an unconfirmed account, we've sent a fresh confirmation link.",
            "success",
        )
        return redirect(url_for("auth.resend_confirmation"))

    return render_template(
        "auth/resend_confirmation.html",
        title="Confirm your email",
        email_value=email_value,
    )


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
            reset_url = _public_url("auth.reset_password", token=token)

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
