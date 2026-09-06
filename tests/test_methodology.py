from decimal import Decimal

from core import create_app
from core.models.city import City


def test_city_cost_formula_includes_backpacker_buffer():
    city = City(
        name="Example",
        country_id=1,
        hostel_per_night=Decimal("20"),
        monthly_living_cost=Decimal("600"),
    )

    assert city.balanced_cost == 43.33
    assert city.shoestring_cost == 31.20
    assert city.comfortable_cost == 67.16


def test_methodology_page_is_public():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-not-for-production",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
    })

    response = app.test_client().get("/how-costs-work")

    assert response.status_code == 200
    assert b"Useful estimates" in response.data
    assert b"monthly living + \xc2\xa3100" in response.data
    assert b"Balanced \xc3\x97 0.72" in response.data
