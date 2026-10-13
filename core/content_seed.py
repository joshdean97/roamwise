"""Import reviewed, source-backed private reel templates atomically."""
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import unicodedata

from core.extensions import db
from core.models.city import City
from core.models.country import Country
from core.models.trip import Trip, TripLeg, TripStop
from core.models.user import User

DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "reel-trips-2026-10.json"


def _name_key(value):
    value = value.split(" / ", 1)[0]
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().strip().lower()


def import_content_templates(dataset, owner):
    if not owner.is_admin or not owner.is_internal:
        raise ValueError("Content templates require an internal administrator owner")
    if len(dataset["trips"]) != 50:
        raise ValueError("The reviewed collection must contain exactly 50 trips")
    if len({t['key'] for t in dataset['trips']}) != 50:
        raise ValueError("Duplicate content source key")

    countries = {country.code: country for country in Country.query.all()}
    cities = {(city.country.code, _name_key(city.name)): city for city in City.query.all()}
    counts = {"countries": 0, "cities": 0, "trips": 0, "existing_trips": 0}

    for item in dataset["cities"]:
        key = (item["country_code"], _name_key(item["name"]))
        if key in cities:
            continue  # Preserve established destination prices and metadata.
        if not item.get("numbeo") or not item.get("hostelworld", {}).get("samples"):
            raise ValueError(f"Missing required city cost sources for {item['name']}")
        country = countries.get(item["country_code"])
        if country is None:
            details = dataset["countries"][item["country_code"]]
            country = Country(code=item["country_code"], **details)
            db.session.add(country)
            db.session.flush()
            countries[country.code] = country
            counts["countries"] += 1
        proxy = item["numbeo"].get("scope") != "city"
        city = City(
            name=item["name"], country_id=country.id, region=country.region,
            hostel_per_night=Decimal(str(item["hostel_gbp"])),
            monthly_living_cost=Decimal(str(item["living_monthly_gbp"])),
            price_checked_at=datetime.fromisoformat(dataset["checked_at"]),
            price_source=("Numbeo " + (f"{item['numbeo'].get('proxy_city', item['numbeo'].get('proxy_country', country.name))} {item['numbeo'].get('scope')}" if proxy else "city monthly excl. rent") + "; Hostelworld mean advertised dorm starting prices; checked 2026-10-13")[:255],
            price_confidence="low" if proxy else "medium",
        )
        db.session.add(city)
        db.session.flush()
        cities[key] = city
        counts["cities"] += 1

    for item in dataset["trips"]:
        existing = Trip.query.filter_by(content_source_key=item["key"]).first()
        if existing:
            if existing.user_id != owner.id:
                raise ValueError("Content source key belongs to another owner")
            existing.is_public = False
            existing.share_token = None
            existing.is_content_template = True
            counts["existing_trips"] += 1
            continue
        if len(item["stops"]) != 3 or len(item["legs"]) != 2:
            raise ValueError("Every reel template needs three stops and two legs")
        trip = Trip(
            user_id=owner.id, name=item["name"], travel_style="balanced",
            display_currency="GBP", fx_rate=1, is_public=False,
            share_token=None, is_content_template=True,
            content_source_key=item["key"], content_research={
                "checked_at": dataset["checked_at"],
                "fx": dataset["fx"], "highlights": item["highlights"],
                "transport": item["legs"], "stay_sources": [
                    next((c for c in dataset["cities"] if c["country_code"] == stop["country_code"] and _name_key(c["name"]) == _name_key(stop["city"])),
                         {"name": stop["city"], "scope": "existing LeavePrints city snapshot; not reverified in this import"})
                    for stop in item["stops"]
                ], "exclusions": dataset["exclusions"],
            },
        )
        db.session.add(trip)
        for position, stop in enumerate(item["stops"], 1):
            city = cities[(stop["country_code"], _name_key(stop["city"]))]
            hostel = float(city.hostel_per_night)
            daily = city.balanced_cost
            trip.stops.append(TripStop(
                city_id=city.id, position=position, nights=stop["nights"],
                daily_cost_gbp=daily, hostel_per_night_gbp=hostel,
                living_per_day_gbp=round(daily - hostel, 2),
            ))
        for position, leg in enumerate(item["legs"], 1):
            if not leg.get("source_url") or float(leg["budget_gbp"]) <= 0:
                raise ValueError("Every transport leg requires a positive sourced budget")
            from_stop, to_stop = item["stops"][position-1:position+1]
            trip.legs.append(TripLeg(
                position=position,
                from_city_id=cities[(from_stop["country_code"], _name_key(from_stop["city"]))].id,
                to_city_id=cities[(to_stop["country_code"], _name_key(to_stop["city"]))].id,
                mode=leg["mode"], cost_gbp=leg["budget_gbp"],
                note=(f"Estimate; checked 2026-10-13. {leg['source_url']}")[:200],
            ))
        counts["trips"] += 1
    db.session.flush()
    return counts


def seed_reviewed_collection():
    owner = User.query.filter_by(
        username="joshtravels",
        is_admin=True, is_internal=True,
    ).first()
    if not owner:
        return {"skipped": "Collection owner not present"}
    dataset = json.loads(DATASET_PATH.read_text())
    try:
        counts = import_content_templates(dataset, owner)
        db.session.commit()
        return counts
    except Exception:
        db.session.rollback()
        raise
