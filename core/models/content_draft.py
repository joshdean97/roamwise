from datetime import datetime, timezone

from core.extensions import db


DRAFT_STATUSES = {"ready", "approved", "rejected", "posted"}
ACTIVE_DRAFT_STATUSES = {"ready", "approved", "posted"}


class ContentDraft(db.Model):
    """A rendered social asset waiting for manual review or publication."""

    __tablename__ = "content_draft"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trip.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_key = db.Column(db.String(64), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
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
    status = db.Column(
        db.String(20),
        nullable=False,
        default="ready",
        server_default="ready",
        index=True,
    )
    headline = db.Column(db.String(500), nullable=True)
    caption = db.Column(db.Text, nullable=False)
    overlay_text = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(120), nullable=True)
    pexels_video_id = db.Column(db.String(64), nullable=True)
    pexels_page_url = db.Column(db.String(1000), nullable=True)
    pexels_attribution = db.Column(db.String(255), nullable=True)
    render_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    render_url = db.Column(db.String(1000), nullable=False)
    snapshot_url = db.Column(db.String(1000), nullable=True)
    posted_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    trip = db.relationship("Trip", back_populates="content_drafts")

    __table_args__ = (
        db.UniqueConstraint(
            "batch_key",
            "position",
            name="uq_content_draft_batch_position",
        ),
        db.Index(
            "ix_content_draft_trip_platform_format_status",
            "trip_id",
            "platform",
            "format",
            "status",
        ),
    )
