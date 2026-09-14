from core.extensions import db


class CityPriceSnapshot(db.Model):
    """Immutable record of the city prices used by LeavePrints at a point in time."""

    __tablename__ = "city_price_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    city_id = db.Column(
        db.Integer,
        db.ForeignKey("city.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hostel_per_night = db.Column(db.Numeric(10, 2), nullable=False)
    monthly_living_cost = db.Column(db.Numeric(10, 2), nullable=False)
    balanced_daily_cost = db.Column(db.Numeric(10, 2), nullable=False)
    source = db.Column(
        db.String(32),
        nullable=False,
        default="admin_update",
        server_default="admin_update",
    )
    recorded_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        index=True,
    )

    city = db.relationship(
        "City",
        backref=db.backref(
            "price_snapshots",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="CityPriceSnapshot.recorded_at",
        ),
    )

    @classmethod
    def record(cls, city, source="admin_update"):
        snapshot = cls(
            city=city,
            hostel_per_night=city.hostel_per_night,
            monthly_living_cost=city.monthly_living_cost,
            balanced_daily_cost=city.balanced_cost,
            source=source,
        )
        db.session.add(snapshot)
        return snapshot
