from datetime import datetime, timezone

import pytest

from core import create_app
from core.analytics import capture_event
from core.extensions import db
from core.models.analytics_event import AnalyticsEvent
from core.models.city import City
from core.models.city_price_snapshot import CityPriceSnapshot
from core.models.country import Country
from core.models.trip import Trip, TripStop
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

        traveller = User(
            username="analytics-traveller",
            email="traveller@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
            is_admin=False,
        )
        traveller.set_password("test-password")
        db.session.add(traveller)

        country = Country(
            name="Bulgaria",
            code="BG",
            currency_code="GBP",
            region="Balkans",
            is_schengen=True,
            visa_buffer=False,
        )
        db.session.add(country)
        db.session.flush()
        db.session.add(City(
            name="Sofia",
            region="Balkans",
            country_id=country.id,
            hostel_per_night=15,
            monthly_living_cost=500,
        ))
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


def test_capture_event_deduplicates_immediate_authenticated_retries(app):
    with app.app_context():
        assert capture_event(
            "login_completed",
            user_id=42,
            properties={"source": "password"},
        )
        assert not capture_event(
            "login_completed",
            user_id=42,
            properties={"source": "password"},
        )
        assert AnalyticsEvent.query.count() == 1


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


def test_landing_event_keeps_sanitised_campaign_attribution(app, client):
    response = client.get(
        "/?utm_source=instagram&utm_medium=bio&utm_campaign=rome%20reel!"
    )
    assert response.status_code == 200

    with app.app_context():
        event = AnalyticsEvent.query.filter_by(name="landing_viewed").one()
        assert event.properties == {
            "authenticated": False,
            "utm_source": "instagram",
            "utm_medium": "bio",
            "utm_campaign": "romereel",
        }


def test_admin_analytics_page_is_available(app, client):
    login_test_user(client, app)

    response = client.get("/admin/analytics")
    assert response.status_code == 200
    assert b"Content intelligence" in response.data


def test_non_admin_cannot_open_analytics_dashboard(app, client):
    with app.app_context():
        user = User.query.filter_by(email="traveller@example.com").one()
        user_id = user.id

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/admin/analytics")
    assert response.status_code == 403


def test_admin_price_change_creates_immutable_history(app, client):
    login_test_user(client, app)
    with app.app_context():
        city = City.query.filter_by(name="Sofia").one()
        city_id = city.id
        country_id = city.country_id

    response = client.post(
        f"/city/{city_id}/update",
        data={
            "name": "Sofia",
            "region": "Balkans",
            "country_id": country_id,
            "hostel_per_night": "18.00",
            "monthly_living_cost": "520.00",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        snapshot = CityPriceSnapshot.query.one()
        assert snapshot.city_id == city_id
        assert float(snapshot.hostel_per_night) == 18
        assert float(snapshot.monthly_living_cost) == 520
        assert snapshot.source == "admin_update"


def test_admin_analytics_renders_trip_and_price_sections(app, client):
    login_test_user(client, app)
    response = client.get("/admin/analytics")
    assert response.status_code == 200
    assert b"Content intelligence" in response.data
    assert b"Historical cost data" in response.data


def test_admin_analytics_excludes_internal_user_events(app, client):
    with app.app_context():
        admin = User.query.filter_by(email="analytics@example.com").one()
        traveller = User.query.filter_by(email="traveller@example.com").one()

        capture_event(
            "planner_opened",
            admin.id,
            properties={"source": "internal-marker"},
        )
        capture_event(
            "planner_opened",
            traveller.id,
            properties={"source": "customer-marker"},
        )

    login_test_user(client, app)
    response = client.get("/admin/analytics")

    assert response.status_code == 200
    assert b"customer-marker" in response.data
    assert b"internal-marker" not in response.data
    assert b"internal account" in response.data


def test_admin_analytics_excludes_internal_trips_from_content_signals(app, client):
    with app.app_context():
        admin = User.query.filter_by(email="analytics@example.com").one()
        traveller = User.query.filter_by(email="traveller@example.com").one()
        city = City.query.filter_by(name="Sofia").one()

        internal_trip = Trip(
            user_id=admin.id,
            name="Internal only route",
            travel_style="balanced",
            display_currency="GBP",
            fx_rate=1,
        )
        customer_trip = Trip(
            user_id=traveller.id,
            name="Customer route",
            travel_style="balanced",
            display_currency="GBP",
            fx_rate=1,
        )
        db.session.add_all([internal_trip, customer_trip])
        db.session.flush()
        for trip in (internal_trip, customer_trip):
            db.session.add(TripStop(
                trip_id=trip.id,
                city_id=city.id,
                position=1,
                nights=2,
                daily_cost_gbp=40,
                hostel_per_night_gbp=15,
                living_per_day_gbp=25,
            ))
        db.session.commit()

    login_test_user(client, app)
    response = client.get("/admin/analytics")

    assert response.status_code == 200
    assert b"Customer route" in response.data
    assert b"Internal only route" not in response.data
