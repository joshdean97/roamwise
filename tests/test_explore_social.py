from datetime import datetime, timezone

import pytest

from core import create_app
from core.extensions import db
from core.models.city import City
from core.models.country import Country
from core.models.trip import Trip, TripStop
from core.models.trip_engagement import ENGAGEMENT_SAVE, ENGAGEMENT_USE, TripEngagement
from core.models.user import User


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "ANALYTICS_ENABLED": False,
        "PUBLIC_APP_URL": "https://leaveprints.example",
    })

    with app.app_context():
        db.create_all()

        country = Country(
            name="Testland",
            code="TT",
            currency_code="GBP",
            region="Test",
            is_schengen=False,
            visa_buffer=True,
        )
        db.session.add(country)
        db.session.flush()

        city = City(
            name="Trail City",
            country_id=country.id,
            region="Test",
            hostel_per_night=20,
            monthly_living_cost=600,
        )
        db.session.add(city)

        creator = User(
            username="creator",
            email="creator@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
        )
        creator.set_password("password123")
        traveller = User(
            username="traveller",
            email="traveller@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
        )
        traveller.set_password("password123")
        db.session.add_all([creator, traveller])
        db.session.flush()

        public_trip = Trip(
            user_id=creator.id,
            name="Trail City",
            travel_style="balanced",
            display_currency="GBP",
            fx_rate=1,
            is_public=True,
            share_token="public-token",
        )
        private_trip = Trip(
            user_id=creator.id,
            name="Secret City",
            travel_style="balanced",
            display_currency="GBP",
            fx_rate=1,
            is_public=False,
        )
        db.session.add_all([public_trip, private_trip])
        db.session.flush()

        db.session.add(
            TripStop(
                trip_id=public_trip.id,
                city_id=city.id,
                position=1,
                nights=2,
                daily_cost_gbp=43.33,
                hostel_per_night_gbp=20,
                living_per_day_gbp=23.33,
            )
        )
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, email="traveller@example.com"):
    return client.post(
        "/auth/login",
        data={"email": email, "password": "password123"},
        follow_redirects=True,
    )


def test_explore_only_lists_public_trips(client):
    response = client.get("/explore")
    assert response.status_code == 200
    assert b"Trail City" in response.data
    assert b"Secret City" not in response.data


def test_save_toggle_creates_one_engagement(app, client):
    login(client)
    response = client.post(
        "/share/public-token/save",
        data={"action": "save", "return_to": "explore"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        rows = TripEngagement.query.filter_by(kind=ENGAGEMENT_SAVE).all()
        assert len(rows) == 1

    # Saving it twice must not stack points.
    client.post(
        "/share/public-token/save",
        data={"action": "save", "return_to": "explore"},
    )
    with app.app_context():
        assert TripEngagement.query.filter_by(kind=ENGAGEMENT_SAVE).count() == 1


def test_creator_cannot_save_own_print(app, client):
    login(client, "creator@example.com")
    client.post(
        "/share/public-token/save",
        data={"action": "save", "return_to": "explore"},
    )
    with app.app_context():
        assert TripEngagement.query.count() == 0


def test_using_shared_route_records_attribution_and_unique_use(app, client):
    login(client)

    response = client.get("/plan-trip?use=public-token")
    assert response.status_code == 200
    assert b'public-token' in response.data

    post_data = {
        "route_json": '[{"position":1,"city_id":1,"nights":2}]',
        "transport_json": '{"arrival":{},"departure":{},"legs":[]}',
        "travel_style": "balanced",
        "display_currency": "GBP",
        "start_date": "",
        "end_date": "",
        "source_share_token": "public-token",
    }
    response = client.post("/plan-trip", data=post_data, follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        creator_trip = Trip.query.filter_by(share_token="public-token").one()
        copied = Trip.query.filter(
            Trip.user_id != creator_trip.user_id,
            Trip.source_trip_id == creator_trip.id,
        ).one()
        assert copied.source_trip_id == creator_trip.id
        assert TripEngagement.query.filter_by(
            trip_id=creator_trip.id,
            kind=ENGAGEMENT_USE,
        ).count() == 1

    # A second copied trip by the same traveller keeps attribution but does not
    # award another creator-use point.
    client.post("/plan-trip", data=post_data)
    with app.app_context():
        assert TripEngagement.query.filter_by(kind=ENGAGEMENT_USE).count() == 1
