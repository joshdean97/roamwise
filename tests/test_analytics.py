from datetime import datetime, timezone

import pytest

from core import create_app
from core.analytics import capture_event
from core.extensions import db
from core.models.analytics_event import AnalyticsEvent
from core.models.user import User


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "analytics-test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "ANALYTICS_ENABLED": True,
    })

    with app.app_context():
        db.create_all()
        user = User(
            username="analytics-admin",
            email="analytics@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
            is_admin=True,
        )
        user.set_password("test-password")
        db.session.add(user)
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login_test_user(client, app):
    with app.app_context():
        user = User.query.filter_by(email="analytics@example.com").one()
        user_id = user.id

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    return user_id


def test_capture_event_keeps_only_safe_primitive_properties(app):
    with app.app_context():
        assert capture_event(
            "trip_saved",
            user_id=7,
            properties={
                "stop_count": 3,
                "travel_style": "balanced",
                "nested": {"do_not": "store"},
            },
        )

        event = AnalyticsEvent.query.one()
        assert event.name == "trip_saved"
        assert event.user_id == 7
        assert event.properties == {
            "stop_count": 3,
            "travel_style": "balanced",
        }


def test_client_milestone_endpoint_requires_login(app, client):
    response = client.post(
        "/analytics/event",
        json={"event": "first_city_added"},
    )
    assert response.status_code in {302, 401}

    user_id = login_test_user(client, app)
    response = client.post(
        "/analytics/event",
        json={"event": "first_city_added"},
    )
    assert response.status_code == 200

    with app.app_context():
        event = AnalyticsEvent.query.filter_by(name="first_city_added").one()
        assert event.user_id == user_id


def test_admin_analytics_page_is_available(app, client):
    login_test_user(client, app)

    response = client.get("/admin/analytics")
    assert response.status_code == 200
    assert b"LeavePrints analytics" in response.data
