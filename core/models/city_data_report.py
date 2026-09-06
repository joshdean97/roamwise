from core.extensions import db


REPORT_CATEGORY_LABELS = {
    "hostel_price": "Hostel price",
    "living_cost": "Living costs",
    "daily_estimate": "Daily estimate",
    "other": "Other",
}

REPORT_STATUSES = {"open", "resolved", "dismissed"}


class CityDataReport(db.Model):
    """A traveller-submitted report that a city's cost data may be wrong.

    The city and user foreign keys are nullable with SET NULL semantics so a
    report can remain useful after an account or destination is deleted. A
    small cost snapshot records what the traveller actually saw at submission.
    """

    __tablename__ = "city_data_report"

    id = db.Column(db.Integer, primary_key=True)

    city_id = db.Column(
        db.Integer,
        db.ForeignKey("city.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    city_name_snapshot = db.Column(db.String(100), nullable=False)
    country_name_snapshot = db.Column(db.String(100), nullable=False)

    category = db.Column(db.String(40), nullable=False)
    message = db.Column(db.Text, nullable=False)
    source_url = db.Column(db.String(500), nullable=True)

    hostel_per_night_snapshot = db.Column(db.Numeric(10, 2), nullable=False)
    monthly_living_cost_snapshot = db.Column(db.Numeric(10, 2), nullable=False)
    balanced_daily_snapshot = db.Column(db.Numeric(10, 2), nullable=False)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="open",
        server_default="open",
        index=True,
    )

    resolution_note = db.Column(db.String(500), nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        index=True,
    )

    resolved_at = db.Column(db.DateTime, nullable=True)

    city = db.relationship("City")
    reporter = db.relationship("User")

    @property
    def category_label(self):
        return REPORT_CATEGORY_LABELS.get(self.category, "Other")
