from datetime import datetime, timedelta, timezone

import pytest

from core import create_app
from core.extensions import db
from core.mail import send_onboarding_email
from core.models.user import User
from core.onboarding import send_due_onboarding_emails


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-not-for-production",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "PUBLIC_APP_URL": "https://leaveprints.example",
        "SMTP_HOST": "smtp.example.com",
        "MAIL_FROM": "LeavePrints <no-reply@leaveprints.example>",
        "MAIL_REPLY_TO": "hello@leaveprints.example",
        "ONBOARDING_EMAILS_ENABLED": True,
        "ONBOARDING_EMAIL_DELAY_HOURS": 72,
    })

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.drop_all()


def make_user(username, created_at, confirmed=True, sent_at=None):
    user = User(
        username=username,
        email=f"{username}@example.com",
        created_at=created_at,
        email_confirmed_at=created_at if confirmed else None,
        onboarding_email_sent_at=sent_at,
    )
    user.set_password("test-password")
    db.session.add(user)
    return user


def test_only_due_verified_users_receive_onboarding_email(app, monkeypatch):
    now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
    sent_to = []

    with app.app_context():
        due = make_user("due", now - timedelta(hours=73))
        make_user("recent", now - timedelta(hours=71))
        make_user("unverified", now - timedelta(days=7), confirmed=False)
        admin = make_user("admin", now - timedelta(days=7))
        admin.is_admin = True
        already_sent = make_user(
            "already-sent",
            now - timedelta(days=7),
            sent_at=now - timedelta(days=2),
        )
        db.session.commit()

        monkeypatch.setattr(
            "core.onboarding.send_onboarding_email",
            lambda user, planner_url: sent_to.append((user.email, planner_url)),
        )

        result = send_due_onboarding_emails(now=now)

        assert result == {"candidates": 1, "sent": 1, "failed": 0}
        assert sent_to == [("due@example.com", "https://leaveprints.example/plan-trip")]
        sent_at = db.session.get(User, due.id).onboarding_email_sent_at
        assert sent_at.replace(tzinfo=timezone.utc) == now
        assert db.session.get(User, already_sent.id).onboarding_email_sent_at is not None

        second_result = send_due_onboarding_emails(now=now)
        assert second_result == {"candidates": 0, "sent": 0, "failed": 0}


def test_failed_delivery_is_released_for_retry(app, monkeypatch):
    now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)

    with app.app_context():
        due = make_user("retry-me", now - timedelta(days=4))
        db.session.commit()

        def fail_delivery(user, planner_url):
            raise OSError("SMTP unavailable")

        monkeypatch.setattr(
            "core.onboarding.send_onboarding_email",
            fail_delivery,
        )

        result = send_due_onboarding_emails(now=now)
        refreshed = db.session.get(User, due.id)

        assert result == {"candidates": 1, "sent": 0, "failed": 1}
        assert refreshed.onboarding_email_sent_at is None
        assert refreshed.onboarding_email_claimed_at is None


def test_onboarding_email_contains_copy_cta_and_reply_to(app, monkeypatch):
    captured = []

    with app.app_context():
        user = make_user("traveller", datetime.now(timezone.utc))
        db.session.commit()
        monkeypatch.setattr("core.mail._send_message", captured.append)

        send_onboarding_email(user, "https://leaveprints.example/plan-trip")

    message = captured[0]
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()

    assert message["Subject"] == "Getting the most out of LeavePrints"
    assert message["Reply-To"] == "hello@leaveprints.example"
    assert "Start with a trip, not individual cities." in plain
    assert "I read all of them." in plain
    assert "https://leaveprints.example/plan-trip" in plain
    assert ">Plan a trip</a>" in html
