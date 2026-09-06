from datetime import datetime, timezone

import pytest

from core import create_app
from core.extensions import db
from core.models.analytics_event import AnalyticsEvent
from core.models.city_data_report import CityDataReport
from core.models.trip import Trip
from core.models.user import User


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "account-management-test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "ANALYTICS_ENABLED": True,
        "PASSWORD_RESET_LOG_LINKS": True,
        "EMAIL_CONFIRMATION_LOG_LINKS": True,
        "PUBLIC_APP_URL": "https://leaveprints.example",
    })

    with app.app_context():
        db.create_all()
        user = User(
            username="traveller",
            email="traveller@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
        )
        user.set_password("current-password")
        db.session.add(user)
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client):
    return client.post(
        "/auth/login",
        data={"email": "traveller@example.com", "password": "current-password"},
        follow_redirects=True,
    )


def test_account_page_requires_login(client):
    response = client.get("/auth/account", follow_redirects=False)
    assert response.status_code in {302, 401}


def test_change_password_requires_current_password(app, client):
    login(client)
    response = client.post(
        "/auth/account/change-password",
        data={
            "current_password": "wrong-password",
            "password": "new-secure-password",
            "confirm_password": "new-secure-password",
        },
        follow_redirects=True,
    )
    assert b"Current password is incorrect" in response.data

    with app.app_context():
        user = User.query.filter_by(email="traveller@example.com").one()
        assert user.check_password("current-password")


def test_change_password_updates_credentials(app, client):
    login(client)
    response = client.post(
        "/auth/account/change-password",
        data={
            "current_password": "current-password",
            "password": "new-secure-password",
            "confirm_password": "new-secure-password",
        },
        follow_redirects=True,
    )
    assert b"Password changed" in response.data

    with app.app_context():
        user = User.query.filter_by(email="traveller@example.com").one()
        assert user.check_password("new-secure-password")
        assert not user.check_password("current-password")


def test_delete_account_removes_linked_data(app, client):
    with app.app_context():
        user = User.query.filter_by(email="traveller@example.com").one()
        trip = Trip(
            user_id=user.id,
            name="Test trip",
            travel_style="balanced",
            display_currency="GBP",
            fx_rate=1,
            is_public=True,
            share_token="test-public-token",
        )
        db.session.add(trip)
        db.session.add(AnalyticsEvent(name="trip_saved", user_id=user.id, properties={}))
        db.session.add(CityDataReport(
            city_id=None,
            user_id=user.id,
            city_name_snapshot="Sofia",
            country_name_snapshot="Bulgaria",
            category="daily_estimate",
            message="The estimate looked too high when I visited.",
            source_url=None,
            hostel_per_night_snapshot=15,
            monthly_living_cost_snapshot=500,
            balanced_daily_snapshot=35,
        ))
        db.session.commit()
        user_id = user.id

    login(client)
    response = client.post(
        "/auth/account/delete",
        data={
            "current_password": "current-password",
            "confirmation": "DELETE",
        },
        follow_redirects=True,
    )
    assert b"Your LeavePrints account has been deleted" in response.data

    with app.app_context():
        assert db.session.get(User, user_id) is None
        assert Trip.query.filter_by(user_id=user_id).count() == 0
        assert CityDataReport.query.filter_by(user_id=user_id).count() == 0
        assert AnalyticsEvent.query.filter_by(user_id=user_id).count() == 0
        assert AnalyticsEvent.query.filter_by(name="account_deleted", user_id=None).count() == 1


def test_delete_account_rejects_wrong_confirmation(app, client):
    login(client)
    response = client.post(
        "/auth/account/delete",
        data={
            "current_password": "current-password",
            "confirmation": "delete",
        },
        follow_redirects=True,
    )
    assert b"Type DELETE exactly" in response.data

    with app.app_context():
        assert User.query.filter_by(email="traveller@example.com").count() == 1
