from flask import current_app

from core.extensions import db
from core.models.analytics_event import AnalyticsEvent


ALLOWED_EVENTS = {
    "landing_viewed",
    "account_created",
    "email_confirmed",
    "login_completed",
    "planner_opened",
    "first_city_added",
    "second_city_added",
    "shared_route_loaded",
    "trip_saved",
    "trip_edited",
    "share_page_viewed",
    "public_share_enabled",
    "public_share_disabled",
    "share_card_downloaded",
    "public_trip_viewed",
}


def _clean_properties(properties):
    """Keep analytics deliberately boring and non-sensitive.

    Only primitive values are accepted and strings are truncated. This prevents
    accidental storage of free-form trip notes, email addresses or large payloads.
    """
    if not isinstance(properties, dict):
        return {}

    cleaned = {}

    for key, value in properties.items():
        key = str(key)[:64]

        if value is None or isinstance(value, (bool, int, float)):
            cleaned[key] = value
            continue

        if isinstance(value, str):
            cleaned[key] = value[:160]

    return cleaned


def capture_event(name, user_id=None, properties=None):
    """Persist one first-party analytics event without breaking the user flow.

    Analytics must never make registration, trip saving or public sharing fail.
    If the event write has a problem, the error is logged and the request keeps
    working normally.
    """
    if not current_app.config.get("ANALYTICS_ENABLED", True):
        return False

    if name not in ALLOWED_EVENTS:
        current_app.logger.warning("Ignored unknown analytics event: %s", name)
        return False

    event = AnalyticsEvent(
        name=name,
        user_id=int(user_id) if user_id is not None else None,
        properties=_clean_properties(properties),
    )

    try:
        db.session.add(event)
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not store analytics event %s", name)
        return False
