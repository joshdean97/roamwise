from datetime import datetime, timezone

import pytest

from core import create_app
from core.extensions import db
from core.models.city import City
from core.models.content_post import ContentPost
from core.models.country import Country
from core.models.trip import Trip, TripLeg, TripStop
from core.models.user import User


API_KEY = "test-content-api-key"
AUTH_HEADERS = {"Authorization": f"Bearer {API_KEY}"}


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": True,
        "RATELIMIT_ENABLED": False,
        "ANALYTICS_ENABLED": False,
        "PUBLIC_APP_URL": "https://leaveprints.example",
        "CONTENT_API_KEY": API_KEY,
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

        first_city = City(
            name="Alpha / Alias",
            country_id=country.id,
            region="Test",
            hostel_per_night=20,
            monthly_living_cost=600,
        )
        second_city = City(
            name="Beta",
            country_id=country.id,
            region="Test",
            hostel_per_night=25,
            monthly_living_cost=650,
        )
        db.session.add_all([first_city, second_city])

        creator = User(
            username="creator",
            email="creator@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
        )
        creator.set_password("password123")
        db.session.add(creator)
        db.session.flush()

        public_trip = Trip(
            user_id=creator.id,
            name="Test route",
            travel_style="balanced",
            display_currency="GBP",
            fx_rate=1,
            is_public=True,
            share_token="public-token",
            arrival_transport_cost_gbp=10,
        )
        private_trip = Trip(
            user_id=creator.id,
            name="Private route",
            travel_style="balanced",
            display_currency="GBP",
            fx_rate=1,
            is_public=False,
        )
        db.session.add_all([public_trip, private_trip])
        db.session.flush()

        db.session.add_all([
            TripStop(
                trip_id=public_trip.id,
                city_id=first_city.id,
                position=1,
                nights=2,
                daily_cost_gbp=40,
                hostel_per_night_gbp=20,
                living_per_day_gbp=20,
            ),
            TripStop(
                trip_id=public_trip.id,
                city_id=second_city.id,
                position=2,
                nights=1,
                daily_cost_gbp=50,
                hostel_per_night_gbp=25,
                living_per_day_gbp=25,
            ),
            TripLeg(
                trip_id=public_trip.id,
                from_city_id=first_city.id,
                to_city_id=second_city.id,
                position=1,
                mode="train",
                cost_gbp=20,
            ),
        ])
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_requires_bearer_token(client):
    response = client.get("/api/admin/content/trips")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"

    response = client.get(
        "/api/admin/content/trips",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401


def test_lists_reel_ready_public_trips(client):
    response = client.get(
        "/api/admin/content/trips?limit=5&unused=true",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["meta"] == {
        "count": 1,
        "limit": 5,
        "unused_only": True,
        "platform": "instagram",
        "format": "trial_reel",
    }

    trip = payload["trips"][0]
    assert trip["title"] == "Test route"
    assert trip["route"] == "Alpha → Beta"
    assert trip["days"] == 3
    assert trip["currency_symbol"] == "£"
    assert trip["destination_names"] == ["Alpha", "Beta"]
    assert trip["reel"]["headline"] == "3 days across Alpha → Beta for £160"
    assert trip["costs"] == {
        "accommodation": 65.0,
        "living": 65.0,
        "transport": 30.0,
        "stay": 130.0,
        "total": 160.0,
        "per_day": 53.33,
    }
    assert trip["share_url"] == "https://leaveprints.example/share/public-token"


def test_mark_used_excludes_trip_from_unused_results(app, client):
    response = client.post(
        "/api/admin/content/trips/1/used",
        headers=AUTH_HEADERS,
        json={
            "platform": "instagram",
            "format": "trial_reel",
            "hook": "Three days for £160",
            "posted_at": "2026-09-18T08:30:00Z",
            "external_media_id": "ig-123",
        },
    )
    assert response.status_code == 201
    assert response.get_json()["content_post"]["trip_id"] == 1

    with app.app_context():
        post = ContentPost.query.one()
        assert post.hook == "Three days for £160"
        assert post.external_media_id == "ig-123"

    unused = client.get(
        "/api/admin/content/trips?unused=true",
        headers=AUTH_HEADERS,
    )
    assert unused.get_json()["trips"] == []

    all_trips = client.get(
        "/api/admin/content/trips?unused=false",
        headers=AUTH_HEADERS,
    )
    assert len(all_trips.get_json()["trips"]) == 1


def test_usage_is_scoped_by_platform_and_format(client):
    client.post(
        "/api/admin/content/trips/1/used",
        headers=AUTH_HEADERS,
        json={"platform": "tiktok", "format": "video"},
    )

    instagram = client.get(
        "/api/admin/content/trips?platform=instagram&format=trial_reel",
        headers=AUTH_HEADERS,
    )
    assert len(instagram.get_json()["trips"]) == 1

    tiktok = client.get(
        "/api/admin/content/trips?platform=tiktok&format=video",
        headers=AUTH_HEADERS,
    )
    assert tiktok.get_json()["trips"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/content/trips?limit=0",
        "/api/admin/content/trips?limit=21",
        "/api/admin/content/trips?limit=nope",
        "/api/admin/content/trips?unused=maybe",
    ],
)
def test_rejects_invalid_list_parameters(client, path):
    response = client.get(path, headers=AUTH_HEADERS)
    assert response.status_code == 400


def test_post_is_csrf_exempt_but_still_requires_api_key(client):
    response = client.post(
        "/api/admin/content/trips/1/used",
        json={},
    )
    assert response.status_code == 401

    response = client.post(
        "/api/admin/content/trips/1/used",
        headers=AUTH_HEADERS,
        json={},
    )
    assert response.status_code == 201
