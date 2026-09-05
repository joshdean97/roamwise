import os

from flask import Flask, current_app, render_template
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from core.models.user import User


def _env_bool(name, default="0"):
    return os.environ.get(name, default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _normalise_database_url(value):
    """Return a SQLAlchemy URL that uses psycopg 3 for PostgreSQL."""
    value = (value or "").strip()

    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]

    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]

    return value


def create_app(test_config=None):
    app = Flask(__name__)

    app_env = os.environ.get("APP_ENV", "development").strip().lower()
    is_production = app_env == "production"

    configured_secret = os.environ.get("SECRET_KEY")
    if test_config and not configured_secret:
        configured_secret = test_config.get("SECRET_KEY")

    if not configured_secret:
        raise RuntimeError(
            "SECRET_KEY is not set. Set a long random SECRET_KEY environment "
            "variable before starting Roamwise."
        )

    database_url = _normalise_database_url(
        os.environ.get("DATABASE_URL", "sqlite:///site.db")
    )

    # Tests are allowed to supply their own isolated database directly.
    if test_config and test_config.get("SQLALCHEMY_DATABASE_URI"):
        database_url = _normalise_database_url(
            str(test_config["SQLALCHEMY_DATABASE_URI"])
        )

    if (
        is_production
        and database_url.startswith("sqlite:")
        and not _env_bool("ALLOW_SQLITE_PRODUCTION")
        and not test_config
    ):
        raise RuntimeError(
            "Roamwise is running with APP_ENV=production but DATABASE_URL "
            "still points to SQLite. Configure a production PostgreSQL "
            "DATABASE_URL, or explicitly set ALLOW_SQLITE_PRODUCTION=1."
        )

    public_app_url = (os.environ.get("PUBLIC_APP_URL") or "").rstrip("/")

    if is_production and not public_app_url and not test_config:
        raise RuntimeError(
            "PUBLIC_APP_URL is required in production. Set it to the public "
            "HTTPS origin for Roamwise, for example https://roamwise.app."
        )

    secure_cookie_default = "1" if is_production else "0"

    app.config.update(
        APP_ENV=app_env,
        SECRET_KEY=configured_secret,
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_env_bool(
            "SESSION_COOKIE_SECURE",
            secure_cookie_default,
        ),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=_env_bool(
            "REMEMBER_COOKIE_SECURE",
            secure_cookie_default,
        ),
        PREFERRED_URL_SCHEME="https" if is_production else "http",
        PASSWORD_RESET_MAX_AGE_SECONDS=int(
            os.environ.get("PASSWORD_RESET_MAX_AGE_SECONDS", "3600")
        ),
        PASSWORD_RESET_LOG_LINKS=(
            False
            if is_production
            else _env_bool("PASSWORD_RESET_LOG_LINKS")
        ),
        PUBLIC_APP_URL=public_app_url,
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USERNAME=os.environ.get("SMTP_USERNAME", ""),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        SMTP_USE_TLS=_env_bool("SMTP_USE_TLS", "1"),
        SMTP_USE_SSL=_env_bool("SMTP_USE_SSL"),
        MAIL_FROM=os.environ.get("MAIL_FROM", ""),
        RATELIMIT_STORAGE_URI=os.environ.get(
            "RATELIMIT_STORAGE_URI",
            "memory://",
        ),
        RATELIMIT_HEADERS_ENABLED=True,
        ENABLE_HSTS=_env_bool(
            "ENABLE_HSTS",
            "1" if is_production else "0",
        ),
    )

    if test_config:
        app.config.update(test_config)
        if app.config.get("SQLALCHEMY_DATABASE_URI"):
            app.config["SQLALCHEMY_DATABASE_URI"] = _normalise_database_url(
                str(app.config["SQLALCHEMY_DATABASE_URI"])
            )

    # Most managed hosting platforms terminate HTTPS at a reverse proxy.
    # Trust forwarded headers only when explicitly enabled by deployment config.
    if _env_bool("TRUST_PROXY_HEADERS") and not test_config:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
        )

    os.makedirs(app.instance_path, exist_ok=True)

    from core.extensions import csrf, db, limiter, login_manager, migrate

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    from core.routes.admin import admin_bp
    from core.routes.auth import auth_bp
    from core.routes.city import city_bp
    from core.routes.country import country_bp
    from core.routes.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(city_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(country_bp)

    @app.get("/healthz")
    def healthz():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Database health check failed")
            return {"status": "unhealthy"}, 503

        return {"status": "ok"}, 200

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return render_template(
            "errors/429.html",
            title="Too many attempts",
        ), 429

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault(
            "Referrer-Policy",
            "strict-origin-when-cross-origin",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )

        if app.config.get("ENABLE_HSTS"):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000",
            )

        return response

    return app
