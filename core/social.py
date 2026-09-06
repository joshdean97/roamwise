from core.extensions import db
from core.models.trip import Trip
from core.models.trip_engagement import (
    ENGAGEMENT_SAVE,
    ENGAGEMENT_USE,
    POINTS_PER_SAVE,
    POINTS_PER_USE,
    TripEngagement,
)


def social_stats_for_trip_ids(trip_ids):
    trip_ids = [int(value) for value in trip_ids if value is not None]
    stats = {
        trip_id: {"saves": 0, "uses": 0, "points": 0}
        for trip_id in trip_ids
    }

    if not trip_ids:
        return stats

    rows = (
        db.session.query(
            TripEngagement.trip_id,
            TripEngagement.kind,
            db.func.count(TripEngagement.id),
        )
        .filter(TripEngagement.trip_id.in_(trip_ids))
        .group_by(TripEngagement.trip_id, TripEngagement.kind)
        .all()
    )

    for trip_id, kind, count in rows:
        if trip_id not in stats:
            continue
        if kind == ENGAGEMENT_SAVE:
            stats[trip_id]["saves"] = int(count)
        elif kind == ENGAGEMENT_USE:
            stats[trip_id]["uses"] = int(count)

    for values in stats.values():
        values["points"] = (
            values["saves"] * POINTS_PER_SAVE
            + values["uses"] * POINTS_PER_USE
        )

    return stats


def creator_impact(user_id):
    trip_ids = [
        row[0]
        for row in db.session.query(Trip.id)
        .filter(Trip.user_id == int(user_id))
        .all()
    ]
    stats = social_stats_for_trip_ids(trip_ids)

    return {
        "points": sum(value["points"] for value in stats.values()),
        "saves": sum(value["saves"] for value in stats.values()),
        "uses": sum(value["uses"] for value in stats.values()),
    }


def saved_trip_ids_for_user(user_id):
    if user_id is None:
        return set()

    return {
        row[0]
        for row in db.session.query(TripEngagement.trip_id)
        .filter(
            TripEngagement.user_id == int(user_id),
            TripEngagement.kind == ENGAGEMENT_SAVE,
        )
        .all()
    }


def ensure_engagement(user_id, trip, kind):
    """Create an engagement once; never reward a creator for self-actions."""
    if not trip or trip.user_id == int(user_id):
        return False

    existing = TripEngagement.query.filter_by(
        user_id=int(user_id),
        trip_id=trip.id,
        kind=kind,
    ).first()

    if existing:
        return False

    db.session.add(
        TripEngagement(
            user_id=int(user_id),
            trip_id=trip.id,
            kind=kind,
        )
    )
    return True
