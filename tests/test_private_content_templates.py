import json
from datetime import datetime, timezone

import pytest

from core import create_app
from core.content_seed import DATASET_PATH, import_content_templates
from core.extensions import db
from core.models.city import City
from core.models.country import Country
from core.models.trip import Trip, TripStop
from core.models.user import User


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True, "SECRET_KEY": "content-tests",
        "SQLALCHEMY_DATABASE_URI": "sqlite://", "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False, "ANALYTICS_ENABLED": False,
        "CONTENT_API_KEY": "test-key", "PUBLIC_APP_URL": "https://example.test",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def owner():
    user = User(username="curator", email="curator@example.test", is_admin=True,
                is_internal=True, email_confirmed_at=datetime.now(timezone.utc))
    user.set_password("unused-test-password")
    db.session.add(user)
    db.session.flush()
    return user


def test_collection_is_atomic_idempotent_and_keeps_existing_prices(app):
    dataset = json.loads(DATASET_PATH.read_text())
    user = owner()
    # Supply the established cities needed by this collection. Their prices
    # intentionally differ from the source file to detect accidental updates.
    new_keys = {(c['country_code'], c['name']) for c in dataset['cities']}
    for stop in [s for t in dataset['trips'] for s in t['stops']]:
        if (stop['country_code'], stop['city']) in new_keys:
            continue
        country = Country.query.filter_by(code=stop['country_code']).first()
        if not country:
            country = Country(name=stop['country_code'], code=stop['country_code'], currency_code='GBP')
            db.session.add(country)
            db.session.flush()
        if not City.query.filter_by(name=stop['city'], country_id=country.id).first():
            db.session.add(City(name=stop['city'], country_id=country.id, hostel_per_night=23,
                                monthly_living_cost=600))
            db.session.flush()
    original = City.query.filter_by(name='Rome').one()
    counts = import_content_templates(dataset, user)
    db.session.commit()
    assert counts['trips'] == 50
    assert counts['cities'] == 45
    assert original.hostel_per_night == 23
    assert original.monthly_living_cost == 600
    assert Trip.query.filter_by(is_public=True).count() == 0
    assert Trip.query.filter(Trip.share_token.isnot(None)).count() == 0
    assert all(len(t.stops) == 3 and len(t.legs) == 2 for t in Trip.query.all())
    for trip in Trip.query.all():
        assert all(leg.cost_gbp > 0 for leg in trip.legs)
        assert trip.total_cost_gbp == round(trip.stay_cost_gbp + trip.transport_cost_gbp, 2)
        assert len(trip.content_research['transport']) == 2
    second = import_content_templates(dataset, user)
    db.session.commit()
    assert second == {'countries': 0, 'cities': 0, 'trips': 0, 'existing_trips': 50}
    assert Trip.query.count() == 50


def test_private_templates_are_eligible_but_other_private_trips_stay_private(app):
    admin = owner()
    country = Country(name='Test', code='TT', currency_code='GBP')
    db.session.add(country)
    db.session.flush()
    city = City(name='Test City', country_id=country.id, hostel_per_night=10, monthly_living_cost=300)
    customer = User(username='customer', email='customer@example.test', is_admin=False)
    customer.set_password('unused')
    db.session.add_all([city, customer])
    db.session.flush()
    template = Trip(user_id=admin.id, name='Private researched template', is_public=False,
                    is_content_template=True, content_research={'checked_at': '2026-10-13'})
    normal = Trip(user_id=admin.id, name='Ordinary private trip', is_public=False)
    customer_trip = Trip(user_id=customer.id, name='Customer private trip', is_public=False,
                         is_content_template=True)
    for trip in [template, normal, customer_trip]:
        trip.stops.append(TripStop(city_id=city.id, position=1, nights=3, daily_cost_gbp=23.33,
                                   hostel_per_night_gbp=10, living_per_day_gbp=13.33))
        db.session.add(trip)
    db.session.commit()
    client = app.test_client()
    headers = {'Authorization': 'Bearer test-key'}
    assert client.get('/api/admin/content/trips').status_code == 401
    response = client.get('/api/admin/content/trips', headers=headers)
    assert [t['id'] for t in response.json['trips']] == [template.id]
    item = response.json['trips'][0]
    assert item['is_public'] is False
    assert item['share_url'] == 'https://example.test/plan-trip'
    assert 'None' not in item['share_url']
    assert 'Estimated' in item['reel']['headline']
    assert 'nights' in item['reel']['overlay_text']
    assert 'Private researched template' not in client.get('/explore').get_data(as_text=True)
    assert client.get('/share/None').status_code == 404

    payload = {'trip_id': template.id, 'caption': 'A researched estimate', 'renders': [
        {'render_status': 'succeeded', 'render_id': f'private-render-{n}',
         'render_url': f'https://media.example.test/{n}.mp4'} for n in range(6)
    ]}
    assert client.post('/api/admin/content/reel-drafts', json=payload, headers=headers).status_code == 201
    assert client.get('/api/admin/content/trips', headers=headers).json['trips'] == []
    assert client.post(f'/api/admin/content/trips/{template.id}/used', json={}, headers=headers).status_code == 201
    for trip in [normal, customer_trip]:
        assert client.post(f'/api/admin/content/trips/{trip.id}/used', json={}, headers=headers).status_code == 404


def test_cannot_import_for_customer(app):
    user = User(username='customer', email='customer@example.test', is_admin=False, is_internal=False)
    with pytest.raises(ValueError, match='internal administrator'):
        import_content_templates(json.loads(DATASET_PATH.read_text()), user)
