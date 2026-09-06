import io
import json
import os
import secrets
from datetime import date
from decimal import Decimal
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from core.analytics import capture_event
from core.extensions import db, limiter
from core.fx import DISPLAY_CURRENCIES, get_exchange_rates
from core.models.city import City
from core.models.trip import Trip, TripLeg, TripStop


main_bp = Blueprint("main", __name__)


TRAVEL_STYLES = {
    "shoestring": 0.72,
    "balanced": 1.0,
    "comfortable": 1.55,
}

MAX_TRIP_STOPS = 30
MAX_NIGHTS_PER_STOP = 90
SUPPORTED_DISPLAY_CURRENCIES = {
    "GBP",
    *DISPLAY_CURRENCIES,
}

TRANSPORT_MODE_LABELS = {
    "": "Not set",
    "bus": "Bus",
    "train": "Train",
    "flight": "Flight",
    "ferry": "Ferry",
    "car": "Car",
    "hitchhike": "Hitchhike",
    "other": "Other",
}

TRANSPORT_MODES = set(TRANSPORT_MODE_LABELS)
MAX_TRANSPORT_COST_GBP = Decimal("10000")
MAX_TRANSPORT_NOTE_LENGTH = 200


def parse_optional_date(value):
    value = (value or "").strip()

    if not value:
        return None

    return date.fromisoformat(value)


def city_daily_cost(city, travel_style):
    if travel_style == "shoestring":
        return float(city.shoestring_cost)

    if travel_style == "comfortable":
        return float(city.comfortable_cost)

    return float(city.balanced_cost)


def load_cities():
    return (
        City.query
        .options(joinedload(City.country))
        .order_by(City.name.asc())
        .all()
    )


def build_city_options(cities):
    city_options = []

    for city in cities:
        city_options.append({
            "id": city.id,
            "name": city.name,
            "region": city.region or "",
            "country": city.country.name,
            "countryCode": getattr(
                city.country,
                "code",
                "",
            ),
            "isSchengen": bool(
                city.country.is_schengen
            ),
            "hostelPerNight": float(
                city.hostel_per_night
            ),
            "monthlyLivingCost": float(
                city.monthly_living_cost
            ),
            "balancedCost": float(
                city.balanced_cost
            ),
            "shoestringCost": float(
                city.shoestring_cost
            ),
            "comfortableCost": float(
                city.comfortable_cost
            ),
        })

    return city_options


def get_owned_trip_or_404(trip_id):
    """Return a trip only when it belongs to the logged-in user."""
    return (
        Trip.query
        .options(
            joinedload(Trip.stops)
            .joinedload(TripStop.city)
            .joinedload(City.country),
            joinedload(Trip.legs),
        )
        .filter(
            Trip.id == trip_id,
            Trip.user_id == current_user.id,
        )
        .first_or_404()
    )



def get_public_trip_or_404(share_token):
    token = (share_token or "").strip()

    if not token or len(token) > 64:
        abort(404)

    return (
        Trip.query
        .options(
            joinedload(Trip.stops)
            .joinedload(TripStop.city)
            .joinedload(City.country),
            joinedload(Trip.legs),
        )
        .filter(
            Trip.share_token == token,
            Trip.is_public.is_(True),
        )
        .first_or_404()
    )


def transport_entry_state(mode, cost_gbp, note):
    return {
        "mode": mode or "",
        "cost_gbp": float(cost_gbp or 0),
        "note": note or "",
    }


def trip_transport_state(trip):
    return {
        "arrival": transport_entry_state(
            trip.arrival_transport_mode,
            trip.arrival_transport_cost_gbp,
            trip.arrival_transport_note,
        ),
        "departure": transport_entry_state(
            trip.departure_transport_mode,
            trip.departure_transport_cost_gbp,
            trip.departure_transport_note,
        ),
        "legs": [
            {
                "position": leg.position,
                "from_city_id": leg.from_city_id,
                "to_city_id": leg.to_city_id,
                **transport_entry_state(
                    leg.mode,
                    leg.cost_gbp,
                    leg.note,
                ),
            }
            for leg in trip.legs
        ],
    }


def empty_transport_state():
    return {
        "arrival": transport_entry_state("", 0, ""),
        "departure": transport_entry_state("", 0, ""),
        "legs": [],
    }

def trip_copy_state(trip):
    return {
        "route": [
            {
                "city_id": stop.city_id,
                "nights": stop.nights,
            }
            for stop in trip.stops
        ],
        "travel_style": trip.travel_style,
        "display_currency": trip.display_currency,
        "start_date": "",
        "end_date": "",
        "transport": trip_transport_state(trip),
    }


def trip_initial_state(trip):
    return {
        "route": [
            {
                "city_id": stop.city_id,
                "nights": stop.nights,
            }
            for stop in trip.stops
        ],
        "travel_style": trip.travel_style,
        "display_currency": trip.display_currency,
        "start_date": (
            trip.start_date.isoformat()
            if trip.start_date
            else ""
        ),
        "end_date": (
            trip.end_date.isoformat()
            if trip.end_date
            else ""
        ),
        "transport": trip_transport_state(trip),
    }


def empty_initial_state():
    return {
        "route": [],
        "travel_style": "balanced",
        "display_currency": "GBP",
        "start_date": "",
        "end_date": "",
        "transport": empty_transport_state(),
    }



def normalise_transport_entry(raw, *, strict):
    if not isinstance(raw, dict):
        raw = {}

    mode = (raw.get("mode") or "").strip().lower()

    if mode not in TRANSPORT_MODES:
        if strict:
            raise ValueError("One of the transport modes is invalid.")
        mode = ""

    note = (raw.get("note") or "").strip()

    if len(note) > MAX_TRANSPORT_NOTE_LENGTH:
        if strict:
            raise ValueError("Transport notes must be 200 characters or fewer.")
        note = note[:MAX_TRANSPORT_NOTE_LENGTH]

    raw_cost = raw.get("cost_gbp", 0)

    if raw_cost in {"", None}:
        cost_gbp = Decimal("0")
    else:
        try:
            cost_gbp = Decimal(str(raw_cost))
        except Exception:
            if strict:
                raise ValueError("One of the transport costs is invalid.")
            cost_gbp = Decimal("0")

    if (
        not cost_gbp.is_finite()
        or cost_gbp < 0
        or cost_gbp > MAX_TRANSPORT_COST_GBP
    ):
        if strict:
            raise ValueError("Each transport cost must be between £0 and £10,000.")
        cost_gbp = Decimal("0")

    cost_gbp = cost_gbp.quantize(Decimal("0.01"))

    return {
        "mode": mode,
        "cost_gbp": cost_gbp,
        "note": note,
    }


def parse_transport_data(route_data, *, strict):
    raw_transport = request.form.get("transport_json", "{}")

    try:
        transport_data = json.loads(raw_transport)
    except (TypeError, json.JSONDecodeError):
        if strict:
            raise ValueError("The transport details could not be read.")
        transport_data = {}

    if not isinstance(transport_data, dict):
        if strict:
            raise ValueError("Invalid transport data.")
        transport_data = {}

    arrival = normalise_transport_entry(
        transport_data.get("arrival", {}),
        strict=strict,
    )
    departure = normalise_transport_entry(
        transport_data.get("departure", {}),
        strict=strict,
    )

    raw_legs = transport_data.get("legs", [])
    if not isinstance(raw_legs, list):
        if strict:
            raise ValueError("Invalid route transport data.")
        raw_legs = []

    submitted_by_position = {}
    for raw_leg in raw_legs:
        if not isinstance(raw_leg, dict):
            if strict:
                raise ValueError("One of the transport legs is invalid.")
            continue
        try:
            position = int(raw_leg.get("position"))
        except (TypeError, ValueError):
            if strict:
                raise ValueError("One of the transport legs is invalid.")
            continue
        submitted_by_position[position] = raw_leg

    legs = []
    for index in range(max(0, len(route_data) - 1)):
        position = index + 1
        from_city_id = route_data[index]["city_id"]
        to_city_id = route_data[index + 1]["city_id"]
        raw_leg = submitted_by_position.get(position, {})

        if raw_leg:
            try:
                submitted_from = int(raw_leg.get("from_city_id"))
                submitted_to = int(raw_leg.get("to_city_id"))
            except (TypeError, ValueError):
                submitted_from = None
                submitted_to = None

            if submitted_from != from_city_id or submitted_to != to_city_id:
                if strict:
                    raise ValueError(
                        "The route changed while transport details were being saved."
                    )
                raw_leg = {}

        entry = normalise_transport_entry(raw_leg, strict=strict)
        legs.append({
            "position": position,
            "from_city_id": from_city_id,
            "to_city_id": to_city_id,
            **entry,
        })

    return {
        "arrival": arrival,
        "departure": departure,
        "legs": legs,
    }


def serialise_transport_state(transport_data):
    def serialise_entry(entry):
        return {
            "mode": entry["mode"],
            "cost_gbp": float(entry["cost_gbp"]),
            "note": entry["note"],
        }

    return {
        "arrival": serialise_entry(transport_data["arrival"]),
        "departure": serialise_entry(transport_data["departure"]),
        "legs": [
            {
                "position": leg["position"],
                "from_city_id": leg["from_city_id"],
                "to_city_id": leg["to_city_id"],
                **serialise_entry(leg),
            }
            for leg in transport_data["legs"]
        ],
    }
def planner_state_from_request():
    """
    Rebuild the user's submitted planner state after a validation error.

    Only safe, displayable values are retained. This prevents a typo in
    one field from wiping the whole route the user just built.
    """
    raw_route = request.form.get("route_json", "[]")

    try:
        route_data = json.loads(raw_route)
    except (TypeError, json.JSONDecodeError):
        route_data = []

    route = []

    if isinstance(route_data, list):
        for stop in route_data[:MAX_TRIP_STOPS]:
            if not isinstance(stop, dict):
                continue

            try:
                city_id = int(stop.get("city_id"))
                nights = int(stop.get("nights", 1))
            except (TypeError, ValueError):
                continue

            if city_id < 1:
                continue

            route.append({
                "city_id": city_id,
                "nights": max(
                    1,
                    min(MAX_NIGHTS_PER_STOP, nights),
                ),
            })

    travel_style = request.form.get(
        "travel_style",
        "balanced",
    )

    if travel_style not in TRAVEL_STYLES:
        travel_style = "balanced"

    display_currency = (
        request.form.get(
            "display_currency",
            "GBP",
        )
        .strip()
        .upper()
    )

    if display_currency not in SUPPORTED_DISPLAY_CURRENCIES:
        display_currency = "GBP"

    safe_route_for_transport = [
        {
            "city_id": stop["city_id"],
            "nights": stop["nights"],
        }
        for stop in route
    ]

    transport = parse_transport_data(
        safe_route_for_transport,
        strict=False,
    )

    return {
        "route": route,
        "travel_style": travel_style,
        "display_currency": display_currency,
        "start_date": request.form.get("start_date", ""),
        "end_date": request.form.get("end_date", ""),
        "transport": serialise_transport_state(transport),
    }


def parse_route_data():
    raw_route = request.form.get(
        "route_json",
        "[]",
    )

    try:
        route_data = json.loads(raw_route)
    except (TypeError, json.JSONDecodeError):
        raise ValueError(
            "The route could not be read. Please try saving again."
        )

    if not isinstance(route_data, list):
        raise ValueError("Invalid route data.")

    if not route_data:
        raise ValueError(
            "Add at least one city before saving."
        )

    if len(route_data) > MAX_TRIP_STOPS:
        raise ValueError(
            f"A trip can contain up to {MAX_TRIP_STOPS} stops."
        )

    normalised = []

    for stop in route_data:
        if not isinstance(stop, dict):
            raise ValueError(
                "One of the route stops is invalid."
            )

        try:
            city_id = int(stop.get("city_id"))
            nights = int(stop.get("nights", 1))
        except (TypeError, ValueError):
            raise ValueError(
                "One of the route stops is invalid."
            )

        if city_id < 1:
            raise ValueError(
                "One of the route stops is invalid."
            )

        if nights < 1 or nights > MAX_NIGHTS_PER_STOP:
            raise ValueError(
                "Each stop must be between "
                f"1 and {MAX_NIGHTS_PER_STOP} nights."
            )

        normalised.append({
            "city_id": city_id,
            "nights": nights,
        })

    return normalised

def save_trip_form(trip, exchange_rates):
    """Validate planner POST data and write it into a Trip."""
    route_data = parse_route_data()

    transport_data = parse_transport_data(
        route_data,
        strict=True,
    )

    travel_style = request.form.get(
        "travel_style",
        "balanced",
    )

    if travel_style not in TRAVEL_STYLES:
        raise ValueError(
            "Invalid travel style."
        )

    display_currency = (
        request.form.get(
            "display_currency",
            "GBP",
        )
        .strip()
        .upper()
    )

    if display_currency not in SUPPORTED_DISPLAY_CURRENCIES:
        raise ValueError(
            "That display currency is not supported."
        )

    if display_currency not in exchange_rates:
        raise ValueError(
            f"{display_currency} conversion is temporarily unavailable. "
            "Choose GBP or try again shortly."
        )

    try:
        fx_rate = Decimal(
            str(exchange_rates[display_currency])
        )
    except Exception:
        raise ValueError(
            "The selected exchange rate is unavailable."
        )

    if not fx_rate.is_finite() or fx_rate <= 0:
        raise ValueError(
            "The selected exchange rate is invalid."
        )

    start_date = parse_optional_date(
        request.form.get("start_date")
    )

    end_date = parse_optional_date(
        request.form.get("end_date")
    )

    if (
        start_date
        and end_date
        and end_date < start_date
    ):
        raise ValueError(
            "End date cannot be before start date."
        )

    city_ids = []

    for stop in route_data:
        if stop["city_id"] not in city_ids:
            city_ids.append(
                stop["city_id"]
            )

    cities = (
        City.query
        .options(joinedload(City.country))
        .filter(City.id.in_(city_ids))
        .all()
    )

    city_by_id = {
        city.id: city
        for city in cities
    }

    if len(city_by_id) != len(city_ids):
        raise ValueError(
            "One or more cities no longer exist."
        )

    first_city = city_by_id[
        route_data[0]["city_id"]
    ]

    last_city = city_by_id[
        route_data[-1]["city_id"]
    ]

    if len(route_data) == 1:
        trip_name = first_city.name
    else:
        trip_name = (
            f"{first_city.name} → "
            f"{last_city.name}"
        )

    trip.name = trip_name
    trip.start_date = start_date
    trip.end_date = end_date
    trip.travel_style = travel_style
    trip.display_currency = display_currency
    trip.fx_rate = fx_rate

    trip.arrival_transport_mode = transport_data["arrival"]["mode"] or None
    trip.arrival_transport_cost_gbp = transport_data["arrival"]["cost_gbp"]
    trip.arrival_transport_note = transport_data["arrival"]["note"] or None

    trip.departure_transport_mode = transport_data["departure"]["mode"] or None
    trip.departure_transport_cost_gbp = transport_data["departure"]["cost_gbp"]
    trip.departure_transport_note = transport_data["departure"]["note"] or None

    db.session.add(trip)
    db.session.flush()

    # Rebuild the stop snapshot from scratch. Validate everything above
    # before touching existing rows so updates remain atomic and easy to
    # roll back if the database commit fails.
    for old_leg in list(trip.legs):
        db.session.delete(old_leg)

    for old_stop in list(trip.stops):
        db.session.delete(old_stop)

    db.session.flush()

    multiplier = TRAVEL_STYLES[
        travel_style
    ]

    for position, stop_data in enumerate(
        route_data,
        start=1,
    ):
        city = city_by_id[
            stop_data["city_id"]
        ]

        nights = stop_data["nights"]

        daily_cost = city_daily_cost(
            city,
            travel_style,
        )

        hostel_per_night = (
            float(city.hostel_per_night)
            * multiplier
        )

        living_per_day = (
            (
                float(
                    city.monthly_living_cost
                )
                + 100
            )
            / 30
            * multiplier
        )

        db.session.add(
            TripStop(
                trip_id=trip.id,
                city_id=city.id,
                position=position,
                nights=nights,
                daily_cost_gbp=Decimal(
                    f"{daily_cost:.2f}"
                ),
                hostel_per_night_gbp=Decimal(
                    f"{hostel_per_night:.2f}"
                ),
                living_per_day_gbp=Decimal(
                    f"{living_per_day:.2f}"
                ),
            )
        )

    for leg_data in transport_data["legs"]:
        db.session.add(
            TripLeg(
                trip_id=trip.id,
                from_city_id=leg_data["from_city_id"],
                to_city_id=leg_data["to_city_id"],
                position=leg_data["position"],
                mode=leg_data["mode"] or None,
                cost_gbp=leg_data["cost_gbp"],
                note=leg_data["note"] or None,
            )
        )

    return trip


def render_planner(

    *,
    exchange_rates,
    initial_trip,
    form_action,
    submit_label,
    is_editing=False,
):
    cities = load_cities()

    selected_currency = initial_trip.get(
        "display_currency",
        "GBP",
    )

    if selected_currency not in exchange_rates:
        selected_currency = "GBP"

    return render_template(
        "trips/plan_trip.html",
        city_options=build_city_options(
            cities
        ),
        exchange_rates=exchange_rates,
        display_currency=selected_currency,
        initial_trip=initial_trip,
        form_action=form_action,
        submit_label=submit_label,
        is_editing=is_editing,
        fx_limited=not SUPPORTED_DISPLAY_CURRENCIES.issubset(
            set(exchange_rates)
        ),
    )




def clean_share_city_name(name):
    """Keep bilingual/alias DB names tidy on a social card."""
    return (name or "").split(" / ", 1)[0].strip()


def get_public_app_url():
    """
    The QR target is deliberately configurable so a future domain change
    does not require changing share-card code.
    """
    configured = (
        current_app.config.get("PUBLIC_APP_URL")
        or os.getenv("PUBLIC_APP_URL")
        or ""
    ).strip()

    if configured:
        if not configured.startswith(("http://", "https://")):
            configured = f"https://{configured}"

        return configured.rstrip("/") + "/"

    return request.url_root.rstrip("/") + "/"



def generate_share_token():
    for _ in range(10):
        token = secrets.token_urlsafe(18)

        exists = (
            db.session.query(Trip.id)
            .filter(Trip.share_token == token)
            .first()
        )

        if not exists:
            return token

    raise RuntimeError(
        "Could not generate a unique public share token."
    )


def public_trip_url(trip):
    if not trip.is_public or not trip.share_token:
        return None

    base = get_public_app_url().rstrip("/")
    path = url_for(
        "main.public_trip",
        share_token=trip.share_token,
    )

    return f"{base}{path}"


def share_qr_target(trip):
    return (
        public_trip_url(trip)
        or get_public_app_url()
    )


def build_share_payload(trip):
    symbol_map = {
        "GBP": "£",
        "EUR": "€",
        "USD": "$",
        "AUD": "A$",
    }

    symbol = symbol_map.get(
        trip.display_currency,
        f"{trip.display_currency} ",
    )

    style_names = {
        "shoestring": "Shoestring backpacker",
        "balanced": "Balanced backpacker",
        "comfortable": "Comfortable backpacker",
    }

    date_label = ""

    if trip.start_date and trip.end_date:
        date_span_nights = (
            trip.end_date - trip.start_date
        ).days

        if date_span_nights == trip.total_nights:
            date_label = (
                f"{trip.start_date.strftime('%d %b %Y')} "
                f"→ {trip.end_date.strftime('%d %b %Y')}"
            )

    stops = []

    for stop in trip.stops:
        stops.append({
            "city": clean_share_city_name(stop.city.name),
            "country": stop.city.country.name,
            "nights": stop.nights,
            "cost": trip.convert_from_gbp(stop.total_cost_gbp),
        })

    legs_by_position = {
        leg.position: leg
        for leg in trip.legs
    }

    transport_legs = []

    for index in range(max(0, len(trip.stops) - 1)):
        position = index + 1
        from_stop = trip.stops[index]
        to_stop = trip.stops[index + 1]
        leg = legs_by_position.get(position)

        if not leg:
            transport_legs.append({
                "position": position,
                "from_city": clean_share_city_name(from_stop.city.name),
                "to_city": clean_share_city_name(to_stop.city.name),
                "mode": "",
                "mode_label": TRANSPORT_MODE_LABELS[""],
                "cost": 0,
                "has_details": False,
            })
            continue

        mode = leg.mode or ""
        transport_legs.append({
            "position": position,
            "from_city": clean_share_city_name(from_stop.city.name),
            "to_city": clean_share_city_name(to_stop.city.name),
            "mode": mode,
            "mode_label": TRANSPORT_MODE_LABELS.get(mode, "Other"),
            "cost": trip.convert_from_gbp(leg.cost_gbp or 0),
            "has_details": bool(mode or float(leg.cost_gbp or 0)),
        })

    arrival_mode = trip.arrival_transport_mode or ""
    departure_mode = trip.departure_transport_mode or ""

    arrival_transport = {
        "mode": arrival_mode,
        "mode_label": TRANSPORT_MODE_LABELS.get(arrival_mode, "Other"),
        "cost": trip.convert_from_gbp(trip.arrival_transport_cost_gbp or 0),
        "has_details": bool(
            arrival_mode
            or float(trip.arrival_transport_cost_gbp or 0)
        ),
    }

    departure_transport = {
        "mode": departure_mode,
        "mode_label": TRANSPORT_MODE_LABELS.get(departure_mode, "Other"),
        "cost": trip.convert_from_gbp(trip.departure_transport_cost_gbp or 0),
        "has_details": bool(
            departure_mode
            or float(trip.departure_transport_cost_gbp or 0)
        ),
    }

    if len(stops) == 1:
        share_name = stops[0]["city"]
    elif stops:
        share_name = f"{stops[0]['city']} → {stops[-1]['city']}"
    else:
        share_name = trip.name

    public_url = public_trip_url(trip)
    qr_target = share_qr_target(trip)
    qr_host = urlparse(qr_target).hostname or ""

    return {
        "trip_id": trip.id,
        "name": share_name,
        "date_label": date_label,
        "currency": trip.display_currency,
        "symbol": symbol,
        "travel_style": style_names.get(
            trip.travel_style,
            trip.travel_style.title(),
        ),
        "total_nights": trip.total_nights,
        "total_cost": trip.total_cost_display,
        "stay_cost": trip.stay_cost_display,
        "transport_cost": trip.transport_cost_display,
        "average_cost": trip.average_cost_display,
        "schengen_nights": trip.schengen_nights,
        "non_schengen_nights": trip.non_schengen_nights,
        "stops": stops,
        "transport": {
            "arrival": arrival_transport,
            "departure": departure_transport,
            "legs": transport_legs,
        },
        "is_public": bool(trip.is_public and trip.share_token),
        "public_url": public_url,
        "qr_points_to_trip": bool(public_url),
        "qr_is_local": qr_host in {"127.0.0.1", "localhost"},
    }


@main_bp.route("/")
def home():
    capture_event(
        "landing_viewed",
        current_user.id if current_user.is_authenticated else None,
        properties={"authenticated": bool(current_user.is_authenticated)},
    )
    return render_template("index.html")


@main_bp.get("/how-costs-work")
def how_costs_work():
    return render_template(
        "info/how_costs_work.html",
        title="How costs work | LeavePrints",
    )


@main_bp.get("/privacy")
def privacy():
    return render_template(
        "legal/privacy.html",
        title="Privacy Policy | LeavePrints",
    )


@main_bp.get("/terms")
def terms():
    return render_template(
        "legal/terms.html",
        title="Terms of Use | LeavePrints",
    )



@main_bp.post("/analytics/event")
@login_required
@limiter.limit("90 per minute")
def analytics_event():
    payload = request.get_json(silent=True) or {}
    event_name = (payload.get("event") or "").strip()

    allowed_client_events = {
        "first_city_added",
        "second_city_added",
        "share_card_downloaded",
    }

    if event_name not in allowed_client_events:
        abort(400)

    capture_event(event_name, current_user.id)
    return {"ok": True}, 200


@main_bp.route(
    "/plan-trip",
    methods=["GET", "POST"],
)
@login_required
def plan_trip():
    exchange_rates = dict(
        get_exchange_rates()
    )
    initial_state = empty_initial_state()

    if request.method == "GET":
        use_token = (
            request.args.get("use")
            or ""
        ).strip()

        if use_token:
            source_trip = get_public_trip_or_404(
                use_token
            )

            initial_state = trip_copy_state(
                source_trip
            )

            if (
                source_trip.display_currency
                not in exchange_rates
            ):
                exchange_rates[
                    source_trip.display_currency
                ] = float(
                    source_trip.fx_rate
                )

            capture_event(
                "shared_route_loaded",
                current_user.id,
                properties={"stop_count": len(source_trip.stops)},
            )

            flash(
                "Shared route loaded. Choose your dates or make any "
                "changes, then save it as your own trip.",
                "success",
            )

        capture_event(
            "planner_opened",
            current_user.id,
            properties={"source": "shared" if use_token else "direct"},
        )

    if request.method == "POST":
        initial_state = planner_state_from_request()

        try:
            trip = Trip(
                user_id=current_user.id,
                name="New trip",
            )

            save_trip_form(
                trip,
                exchange_rates,
            )

            db.session.commit()
            capture_event(
                "trip_saved",
                current_user.id,
                properties={
                    "stop_count": len(trip.stops),
                    "total_nights": trip.total_nights,
                    "travel_style": trip.travel_style,
                    "display_currency": trip.display_currency,
                },
            )

            flash(
                "Trip saved.",
                "success",
            )

            return redirect(
                url_for("main.my_trips")
            )

        except (
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            db.session.rollback()
            flash(str(exc), "error")

        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Unexpected error while saving trip"
            )

            if current_app.debug:
                raise

            flash(
                "We couldn't save the trip just now. "
                "Your route is still here — please try again.",
                "error",
            )

    return render_planner(
        exchange_rates=exchange_rates,
        initial_trip=initial_state,
        form_action=url_for(
            "main.plan_trip"
        ),
        submit_label="Save trip",
    )

@main_bp.route(
    "/trips/<int:trip_id>/edit",
    methods=["GET", "POST"],
)
@login_required
def edit_trip(trip_id):
    trip = get_owned_trip_or_404(
        trip_id
    )

    exchange_rates = dict(
        get_exchange_rates()
    )

    # A saved trip must remain editable even if live FX is temporarily
    # unavailable. This injects only the trip's own saved rate into this
    # request-local dict; it cannot mutate the shared FX cache.
    if trip.display_currency not in exchange_rates:
        exchange_rates[
            trip.display_currency
        ] = float(trip.fx_rate)

    initial_state = trip_initial_state(
        trip
    )

    if request.method == "POST":
        initial_state = planner_state_from_request()

        try:
            save_trip_form(
                trip,
                exchange_rates,
            )

            db.session.commit()
            capture_event(
                "trip_edited",
                current_user.id,
                properties={
                    "stop_count": len(trip.stops),
                    "total_nights": trip.total_nights,
                    "travel_style": trip.travel_style,
                    "display_currency": trip.display_currency,
                },
            )

            flash(
                "Trip updated.",
                "success",
            )

            return redirect(
                url_for("main.my_trips")
            )

        except (
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            db.session.rollback()
            flash(str(exc), "error")

        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Unexpected error while updating trip %s",
                trip_id,
            )

            if current_app.debug:
                raise

            flash(
                "We couldn't update the trip just now. "
                "Your changes are still on screen — please try again.",
                "error",
            )

    return render_planner(
        exchange_rates=exchange_rates,
        initial_trip=initial_state,
        form_action=url_for(
            "main.edit_trip",
            trip_id=trip.id,
        ),
        submit_label="Update trip",
        is_editing=True,
    )


@main_bp.route(
    "/trips/<int:trip_id>/delete",
    methods=["POST"],
)
@login_required
def delete_trip(trip_id):
    trip = get_owned_trip_or_404(
        trip_id
    )

    try:
        db.session.delete(trip)
        db.session.commit()

        flash(
            "Trip deleted.",
            "success",
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error while deleting trip %s",
            trip_id,
        )

        if current_app.debug:
            raise

        flash(
            "We couldn't delete that trip. Please try again.",
            "error",
        )

    return redirect(
        url_for("main.my_trips")
    )





@main_bp.route(
    "/trips/<int:trip_id>/share/visibility",
    methods=["POST"],
)
@login_required
def set_trip_share_visibility(trip_id):
    trip = get_owned_trip_or_404(
        trip_id
    )

    visibility = (
        request.form.get("visibility")
        or ""
    ).strip().lower()

    if visibility not in {
        "public",
        "private",
    }:
        abort(400)

    try:
        if visibility == "public":
            if not trip.share_token:
                trip.share_token = generate_share_token()

            trip.is_public = True

            flash(
                "Public link enabled. Anyone with the link can view "
                "this trip and load the route into their planner.",
                "success",
            )

        elif visibility == "private":
            trip.is_public = False
            trip.share_token = None

            flash(
                "Public link disabled. The old share URL no longer works.",
                "success",
            )

        db.session.commit()
        capture_event(
            "public_share_enabled" if visibility == "public" else "public_share_disabled",
            current_user.id,
            properties={"stop_count": len(trip.stops)},
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Could not change public sharing for trip %s",
            trip_id,
        )

        if current_app.debug:
            raise

        flash(
            "We couldn't change the public sharing setting. "
            "Please try again.",
            "error",
        )

    return redirect(
        url_for(
            "main.share_trip",
            trip_id=trip.id,
        )
    )


@main_bp.route(
    "/share/<share_token>",
    methods=["GET"],
)
def public_trip(share_token):
    trip = get_public_trip_or_404(
        share_token
    )
    share_data = build_share_payload(trip)
    capture_event(
        "public_trip_viewed",
        properties={"stop_count": len(trip.stops)},
    )

    return render_template(
        "trips/public_trip.html",
        trip=trip,
        share_data=share_data,
    )

@main_bp.route(
    "/trips/<int:trip_id>/share",
    methods=["GET"],
)
@login_required
def share_trip(trip_id):
    trip = get_owned_trip_or_404(
        trip_id
    )
    share_data = build_share_payload(trip)
    capture_event(
        "share_page_viewed",
        current_user.id,
        properties={"is_public": bool(trip.is_public)},
    )

    return render_template(
        "trips/share_trip.html",
        trip=trip,
        share_data=share_data,
    )

@main_bp.route(
    "/trips/<int:trip_id>/share/qr.png",
    methods=["GET"],
)
@login_required
def share_trip_qr(trip_id):
    # Keep the QR image behind the same ownership check as the share page.
    trip = get_owned_trip_or_404(
        trip_id
    )

    try:
        import qrcode
    except ImportError:
        abort(
            503,
            description=(
                "QR generation is not installed. "
                "Install qrcode[pil]."
            ),
        )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(
        share_qr_target(trip)
    )
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    response = send_file(
        buffer,
        mimetype="image/png",
        max_age=0,
    )
    response.cache_control.no_store = True
    response.cache_control.no_cache = True

    return response


@main_bp.route("/my-trips")
@login_required
def my_trips():
    trips = (
        Trip.query
        .options(
            joinedload(Trip.stops)
            .joinedload(TripStop.city)
            .joinedload(City.country),
            joinedload(Trip.legs),
        )
        .filter(
            Trip.user_id == current_user.id
        )
        .order_by(
            Trip.created_at.desc()
        )
        .all()
    )

    return render_template(
        "trips/my_trips.html",
        trips=trips,
    )
