import hmac
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.orm import selectinload

from core.extensions import db, limiter
from core.models.city import City
from core.models.content_post import ContentPost
from core.models.trip import Trip, TripLeg, TripStop


content_api_bp = Blueprint(
    "content_api",
    __name__,
    url_prefix="/api/admin/content",
)

DEFAULT_PLATFORM = "instagram"
DEFAULT_FORMAT = "trial_reel"
MAX_TRIPS_PER_REQUEST = 20
MAX_HOOK_LENGTH = 500
MAX_EXTERNAL_MEDIA_ID_LENGTH = 255
MAX_CLASSIFIER_LENGTH = 32


def _json_error(message, status):
    return jsonify({"error": message}), status


def _require_content_api_key(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        configured_key = current_app.config.get("CONTENT_API_KEY", "")

        if not configured_key:
            return _json_error("Content API is not configured", 503)

        authorization = request.headers.get("Authorization", "")
        scheme, separator, supplied_key = authorization.partition(" ")

        if (
            not separator
            or scheme.lower() != "bearer"
            or not hmac.compare_digest(supplied_key, configured_key)
        ):
            response, status = _json_error("Invalid or missing API key", 401)
            response.headers["WWW-Authenticate"] = "Bearer"
            return response, status

        return view(*args, **kwargs)

    return wrapped


def _query_classifier(name, default):
    value = (request.args.get(name) or default).strip().lower()

    if not value or len(value) > MAX_CLASSIFIER_LENGTH:
        raise ValueError(
            f"{name} must be between 1 and {MAX_CLASSIFIER_LENGTH} characters"
        )

    return value


def _parse_boolean(value, default=True):
    if value is None:
        return default

    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off"}:
        return False

    raise ValueError("unused must be true or false")


def _parse_posted_at(value):
    if not value:
        return datetime.now(timezone.utc)

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError("posted_at must be a valid ISO 8601 timestamp") from error

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _public_trip_url(trip):
    base_url = (current_app.config.get("PUBLIC_APP_URL") or request.url_root).rstrip("/")
    return f"{base_url}/share/{trip.share_token}"


def _money(trip, value):
    return trip.convert_from_gbp(value)


def _currency_symbol(currency):
    return {
        "GBP": "£",
        "EUR": "€",
        "USD": "$",
        "AUD": "A$",
    }.get(currency, f"{currency} ")


def _country_flag(code):
    normalised = (code or "").strip().upper()
    if len(normalised) != 2 or not normalised.isalpha():
        return "📍"
    return "".join(chr(127397 + ord(character)) for character in normalised)


def _transport_emoji(mode):
    return {
        "bus": "🚌",
        "coach": "🚌",
        "train": "🚆",
        "rail": "🚆",
        "flight": "✈️",
        "plane": "✈️",
        "ferry": "⛴️",
        "car": "🚗",
    }.get((mode or "").strip().lower(), "🚌")


def _serialize_trip(trip):
    destinations = []

    for stop in trip.stops:
        destinations.append({
            "city": stop.city.name.split(" / ", 1)[0].strip(),
            "country": stop.city.country.name,
            "country_code": stop.city.country.code,
            "nights": stop.nights,
            "accommodation": _money(trip, stop.accommodation_cost_gbp),
            "living": _money(trip, stop.living_cost_gbp),
            "total": _money(trip, stop.total_cost_gbp),
        })

    legs = []

    for leg in trip.legs:
        legs.append({
            "from_city": leg.from_city.name.split(" / ", 1)[0].strip(),
            "to_city": leg.to_city.name.split(" / ", 1)[0].strip(),
            "mode": leg.mode or "transport",
            "cost": _money(trip, leg.cost_gbp),
        })

    destination_names = [item["city"] for item in destinations]
    route = " → ".join(destination_names) or trip.name
    nights = trip.total_nights
    total = trip.total_cost_display
    symbol = _currency_symbol(trip.display_currency)
    country_count = len({item["country_code"] for item in destinations})
    country_word = "country" if country_count == 1 else "countries"

    breakdown_lines = []
    for index, destination in enumerate(destinations):
        day_word = "day" if destination["nights"] == 1 else "days"
        breakdown_lines.append(
            f"{_country_flag(destination['country_code'])} "
            f"{destination['city']} — {destination['nights']} {day_word}: "
            f"{symbol}{destination['total']:.0f}"
        )
        if index < len(legs):
            leg = legs[index]
            breakdown_lines.append(
                f"{_transport_emoji(leg['mode'])} "
                f"{leg['from_city']} → {leg['to_city']}: "
                f"{symbol}{leg['cost']:.0f}"
            )

    overlay_text = "\n".join([
        "I planned my travel costs with this website…",
        "",
        *breakdown_lines,
        "",
        f"{nights} days · {country_count} {country_word} · {symbol}{total:.0f} total",
        "",
        "Hostels + food + daily spending",
        "",
        "Budget your next trip with LeavePrints",
        "Link in bio",
    ])
    caption = "\n".join([
        f"I planned {nights} days across {route} for {symbol}{total:.0f} "
        f"— {symbol}{(total / nights):.0f} per day.",
        "",
        f"Accommodation: {symbol}{_money(trip, trip.accommodation_cost_gbp):.0f}",
        f"Daily spending: {symbol}{_money(trip, trip.living_cost_gbp):.0f}",
        f"Transport: {symbol}{trip.transport_cost_display:.0f}",
        "",
        f"Build your own budget: {_public_trip_url(trip)}",
    ])

    return {
        "id": trip.id,
        "title": trip.name,
        "route": route,
        "destination_names": destination_names,
        "destinations": destinations,
        "legs": legs,
        "days": nights,
        "nights": nights,
        "travel_style": trip.travel_style,
        "currency": trip.display_currency,
        "currency_symbol": symbol,
        "costs": {
            "accommodation": _money(trip, trip.accommodation_cost_gbp),
            "living": _money(trip, trip.living_cost_gbp),
            "transport": trip.transport_cost_display,
            "stay": trip.stay_cost_display,
            "total": total,
            "per_day": round(total / nights, 2) if nights else 0,
        },
        "share_url": _public_trip_url(trip),
        "reel": {
            "headline": f"{nights} days across {route} for {symbol}{total:.0f}",
            "route": route,
            "budget_label": f"{symbol}{total:.0f} total",
            "per_day_label": (
                f"{symbol}{(total / nights):.0f} per day"
                if nights
                else ""
            ),
            "overlay_text": overlay_text,
            "caption": caption,
            "status": "draft",
        },
        "created_at": trip.created_at.isoformat() if trip.created_at else None,
    }


@content_api_bp.get("/trips")
@limiter.limit("60 per minute")
@_require_content_api_key
def list_content_trips():
    try:
        limit = int(request.args.get("limit", "5"))
        unused_only = _parse_boolean(request.args.get("unused"))
        platform = _query_classifier("platform", DEFAULT_PLATFORM)
        content_format = _query_classifier("format", DEFAULT_FORMAT)
    except ValueError as error:
        return _json_error(str(error), 400)

    if not 1 <= limit <= MAX_TRIPS_PER_REQUEST:
        return _json_error(
            f"limit must be between 1 and {MAX_TRIPS_PER_REQUEST}",
            400,
        )

    query = (
        Trip.query
        .options(
            selectinload(Trip.stops)
            .selectinload(TripStop.city)
            .selectinload(City.country),
            selectinload(Trip.legs).selectinload(TripLeg.from_city),
            selectinload(Trip.legs).selectinload(TripLeg.to_city),
        )
        .filter(
            Trip.is_public.is_(True),
            Trip.share_token.isnot(None),
            Trip.stops.any(),
        )
    )

    if unused_only:
        query = query.filter(
            ~Trip.content_posts.any(
                (ContentPost.platform == platform)
                & (ContentPost.format == content_format)
            )
        )

    trips = query.order_by(Trip.created_at.desc(), Trip.id.desc()).limit(limit).all()

    return jsonify({
        "trips": [_serialize_trip(trip) for trip in trips],
        "meta": {
            "count": len(trips),
            "limit": limit,
            "unused_only": unused_only,
            "platform": platform,
            "format": content_format,
        },
    })


@content_api_bp.post("/trips/<int:trip_id>/used")
@limiter.limit("60 per minute")
@_require_content_api_key
def mark_content_trip_used(trip_id):
    trip = Trip.query.filter(
        Trip.id == trip_id,
        Trip.is_public.is_(True),
        Trip.share_token.isnot(None),
    ).first()

    if not trip:
        return _json_error("Public trip not found", 404)

    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return _json_error("JSON body must be an object", 400)

    try:
        platform = str(payload.get("platform") or DEFAULT_PLATFORM).strip().lower()
        content_format = str(payload.get("format") or DEFAULT_FORMAT).strip().lower()
        posted_at = _parse_posted_at(payload.get("posted_at"))
    except ValueError as error:
        return _json_error(str(error), 400)

    if not platform or len(platform) > MAX_CLASSIFIER_LENGTH:
        return _json_error(
            f"platform must be between 1 and {MAX_CLASSIFIER_LENGTH} characters",
            400,
        )
    if not content_format or len(content_format) > MAX_CLASSIFIER_LENGTH:
        return _json_error(
            f"format must be between 1 and {MAX_CLASSIFIER_LENGTH} characters",
            400,
        )

    hook = payload.get("hook")
    if hook is not None:
        hook = str(hook).strip() or None
        if hook and len(hook) > MAX_HOOK_LENGTH:
            return _json_error(
                f"hook must be at most {MAX_HOOK_LENGTH} characters",
                400,
            )

    external_media_id = payload.get("external_media_id")
    if external_media_id is not None:
        external_media_id = str(external_media_id).strip() or None
        if external_media_id and len(external_media_id) > MAX_EXTERNAL_MEDIA_ID_LENGTH:
            return _json_error(
                "external_media_id must be at most "
                f"{MAX_EXTERNAL_MEDIA_ID_LENGTH} characters",
                400,
            )

    post = ContentPost(
        trip_id=trip.id,
        platform=platform,
        format=content_format,
        hook=hook,
        external_media_id=external_media_id,
        posted_at=posted_at,
    )
    db.session.add(post)
    db.session.commit()

    return jsonify({
        "content_post": {
            "id": post.id,
            "trip_id": post.trip_id,
            "platform": post.platform,
            "format": post.format,
            "hook": post.hook,
            "external_media_id": post.external_media_id,
            "posted_at": post.posted_at.isoformat(),
        }
    }), 201
