from datetime import datetime, timezone

import pytest

from core import create_app
from core.extensions import db
from core.models.city import City
from core.models.city_data_report import CityDataReport
from core.models.country import Country
from core.models.user import User


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-not-for-production",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "ANALYTICS_ENABLED": False,
    })

    with app.app_context():
        db.create_all()

        country = Country(
            name="Bulgaria",
            code="BG",
            currency_code="EUR",
            region="Balkans",
            is_schengen=True,
            visa_buffer=False,
        )
        db.session.add(country)
        db.session.flush()

        city = City(
            name="Sofia",
            region="Balkans",
            country_id=country.id,
            hostel_per_night=15,
            monthly_living_cost=500,
        )
        db.session.add(city)

        user = User(
            username="traveller",
            email="traveller@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
        )
        user.set_password("test-password")
        db.session.add(user)

        admin = User(
            username="admin",
            email="admin@example.com",
            email_confirmed_at=datetime.now(timezone.utc),
            is_admin=True,
        )
        admin.set_password("test-password")
        db.session.add(admin)
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, email):
    return client.post(
        "/auth/login",
        data={"email": email, "password": "test-password"},
        follow_redirects=True,
    )


def test_authenticated_user_can_report_city_data(app, client):
    login(client, "traveller@example.com")

    with app.app_context():
        city_id = City.query.filter_by(name="Sofia").one().id

    response = client.post(
        "/data-reports",
        json={
            "city_id": city_id,
            "category": "hostel_price",
            "message": "Dorm beds are closer to £9 right now.",
            "source_url": "https://example.com/hostel",
        },
    )

    assert response.status_code == 201

    with app.app_context():
        report = CityDataReport.query.one()
        assert report.city_name_snapshot == "Sofia"
        assert report.category == "hostel_price"
        assert float(report.hostel_per_night_snapshot) == 15
        assert report.status == "open"


def test_report_endpoint_rejects_invalid_payload(app, client):
    login(client, "traveller@example.com")

    with app.app_context():
        city_id = City.query.filter_by(name="Sofia").one().id

    response = client.post(
        "/data-reports",
        json={
            "city_id": city_id,
            "category": "made_up",
            "message": "too short",
        },
    )

    assert response.status_code == 400
    with app.app_context():
        assert CityDataReport.query.count() == 0


def test_admin_can_resolve_report(app, client):
    with app.app_context():
        city = City.query.filter_by(name="Sofia").one()
        user = User.query.filter_by(email="traveller@example.com").one()
        report = CityDataReport(
            city_id=city.id,
            user_id=user.id,
            city_name_snapshot=city.name,
            country_name_snapshot=city.country.name,
            category="daily_estimate",
            message="The daily estimate looks too high for current prices.",
            hostel_per_night_snapshot=city.hostel_per_night,
            monthly_living_cost_snapshot=city.monthly_living_cost,
            balanced_daily_snapshot=city.balanced_cost,
        )
        db.session.add(report)
        db.session.commit()
        report_id = report.id

    login(client, "admin@example.com")
    response = client.post(
        f"/admin/data-reports/{report_id}/status",
        data={
            "status": "resolved",
            "resolution_note": "Checked and updated source data.",
            "return_status": "open",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        report = db.session.get(CityDataReport, report_id)
        assert report.status == "resolved"
        assert report.resolved_at is not None
        assert report.resolution_note == "Checked and updated source data."
