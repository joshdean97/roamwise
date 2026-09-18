from datetime import datetime, timezone

from core.extensions import db


class ContentPost(db.Model):
    """A social post generated from a LeavePrints trip."""

    __tablename__ = "content_post"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trip.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform = db.Column(
        db.String(32),
        nullable=False,
        default="instagram",
        server_default="instagram",
        index=True,
    )
    format = db.Column(
        db.String(32),
        nullable=False,
        default="trial_reel",
        server_default="trial_reel",
        index=True,
    )
    hook = db.Column(db.String(500), nullable=True)
    external_media_id = db.Column(db.String(255), nullable=True, index=True)
    posted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    trip = db.relationship(
        "Trip",
        back_populates="content_posts",
    )

    __table_args__ = (
        db.Index(
            "ix_content_post_trip_platform_format",
            "trip_id",
            "platform",
            "format",
        ),
    )
