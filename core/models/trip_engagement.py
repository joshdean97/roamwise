from core.extensions import db


ENGAGEMENT_SAVE = "save"
ENGAGEMENT_USE = "use"
ENGAGEMENT_KINDS = {ENGAGEMENT_SAVE, ENGAGEMENT_USE}

POINTS_PER_SAVE = 1
POINTS_PER_USE = 3


class TripEngagement(db.Model):
    """A meaningful action another traveller took on a public Print.

    A traveller can award a creator at most one save and one use per Print.
    This keeps the points system useful without making repeat-click spam valuable.
    """

    __tablename__ = "trip_engagement"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trip.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind = db.Column(
        db.String(16),
        nullable=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        index=True,
    )

    user = db.relationship("User", foreign_keys=[user_id])
    trip = db.relationship("Trip", foreign_keys=[trip_id])

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "trip_id",
            "kind",
            name="uq_trip_engagement_user_trip_kind",
        ),
        db.CheckConstraint(
            "kind IN ('save', 'use')",
            name="ck_trip_engagement_kind",
        ),
    )
