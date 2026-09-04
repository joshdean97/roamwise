from core.extensions import db


class City(db.Model):
    __tablename__ = "city"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        nullable=False
    )

    region = db.Column(
        db.String(100),
        nullable=True
    )

    country_id = db.Column(
        db.Integer,
        db.ForeignKey("country.id"),
        nullable=False,
        index=True
    )

    country = db.relationship(
        "Country",
        back_populates="cities"
    )

    hostel_per_night = db.Column(
        db.Numeric(10, 2),
        nullable=False
    )

    monthly_living_cost = db.Column(
        db.Numeric(10, 2),
        nullable=False
    )

    last_updated = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp()
    )

    __table_args__ = (
        db.UniqueConstraint(
            "name",
            "country_id",
            name="uq_city_country"
        ),
    )

    @property
    def balanced_cost(self):
        return round(
            float(
                (
                    (self.hostel_per_night * 30
                    + self.monthly_living_cost )
                ) / 30
            ),
            2
        )

    @property
    def shoestring_cost(self):
        return round(
            self.balanced_cost * 0.72,
            2
        )

    @property
    def comfortable_cost(self):
        return round(
            self.balanced_cost * 1.55,
            2
        )