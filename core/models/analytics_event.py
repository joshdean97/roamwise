from core.extensions import db


class AnalyticsEvent(db.Model):
    """Small, first-party product analytics event.

    We intentionally do not store IP addresses, user agents, emails or usernames
    here. Authenticated events may contain the internal LeavePrints user id so we
    can measure activation funnels; anonymous page views have no persistent id.
    """

    __tablename__ = "analytics_event"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(64),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    properties = db.Column(
        db.JSON,
        nullable=True,
        default=dict,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        index=True,
    )
