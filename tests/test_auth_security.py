from datetime import datetime, timezone

import pytest

from core import create_app
from core.extensions import db
from core.models.user import User
from core.routes.auth import (
    generate_email_confirmation_token,
    generate_password_reset_token,
    verify_email_confirmation_token,
    verify_password_reset_token,
)


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-not-for-production",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "PASSWORD_RESET_LOG_LINKS": True,
        "EMAIL_CONFIRMATION_LOG_LINKS": True,
        "PUBLIC_APP_URL": "https://leaveprints.example",
    })

    with app.app_context():
        db.create_all()
        user = User(
            username="josh",
            email="josh@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
        )
        user.set_password("old-password")
        db.session.add(user)
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_password_reset_token_stops_working_after_password_change(app):
    with app.app_context():
        user = User.query.filter_by(email="josh@example.com").one()
        token = generate_password_reset_token(user)
        assert verify_password_reset_token(token).id == user.id

        user.set_password("new-password")
        db.session.commit()

        assert verify_password_reset_token(token) is None


def test_unknown_email_gets_generic_forgot_password_response(client):
    response = client.post(
        "/auth/forgot-password",
        data={"email": "nobody@example.com"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"If an account exists for that email" in response.data


def test_reset_password_changes_credentials(app, client):
    with app.app_context():
        user = User.query.filter_by(email="josh@example.com").one()
        token = generate_password_reset_token(user)

    response = client.post(
        f"/auth/reset-password/{token}",
        data={
            "password": "brand-new-password",
            "confirm_password": "brand-new-password",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Password updated" in response.data

    with app.app_context():
        user = User.query.filter_by(email="josh@example.com").one()
        assert user.check_password("brand-new-password")
        assert not user.check_password("old-password")


def test_unconfirmed_user_cannot_log_in(app, client):
    with app.app_context():
        user = User(username="new-user", email="new@example.com")
        user.set_password("test-password")
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/auth/login",
        data={"email": "new@example.com", "password": "test-password"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Confirm your email before logging in" in response.data


def test_confirmation_token_confirms_user(app, client):
    with app.app_context():
        user = User(username="confirm-me", email="confirm@example.com")
        user.set_password("test-password")
        db.session.add(user)
        db.session.commit()
        token = generate_email_confirmation_token(user)
        assert verify_email_confirmation_token(token).id == user.id

    response = client.get(
        f"/auth/confirm-email/{token}",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Email confirmed" in response.data

    with app.app_context():
        user = User.query.filter_by(email="confirm@example.com").one()
        assert user.is_email_confirmed


def test_registration_creates_unconfirmed_account(app, client):
    response = client.post(
        "/auth/register",
        data={
            "username": "fresh-user",
            "email": "fresh@example.com",
            "password": "test-password",
            "confirm_password": "test-password",
            "terms_accepted": "yes",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Account created" in response.data

    with app.app_context():
        user = User.query.filter_by(email="fresh@example.com").one()
        assert not user.is_email_confirmed
        assert user.terms_accepted_at is not None
        assert user.terms_version == "2026-09-05"


def test_login_limit_returns_429_when_enabled():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-not-for-production",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": True,
        "RATELIMIT_STORAGE_URI": "memory://",
    })

    with app.app_context():
        db.create_all()

    client = app.test_client()

    statuses = []
    for _ in range(11):
        response = client.post(
            "/auth/login",
            data={"email": "x@example.com", "password": "wrong"},
        )
        statuses.append(response.status_code)

    assert statuses[-1] == 429
