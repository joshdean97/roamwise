from core.extensions import db


class Trip(db.Model):
    __tablename__ = "trip"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    name = db.Column(
        db.String(200),
        nullable=False,
    )

    start_date = db.Column(
        db.Date,
        nullable=True,
    )

    end_date = db.Column(
        db.Date,
        nullable=True,
    )

    travel_style = db.Column(
        db.String(20),
        nullable=False,
        default="balanced",
    )

    display_currency = db.Column(
        db.String(3),
        nullable=False,
        default="GBP",
    )

    # The GBP -> display currency rate at the moment the trip was saved.
    # This keeps an old saved estimate from changing just because FX moves.
    fx_rate = db.Column(
        db.Numeric(12, 6),
        nullable=False,
        default=1,
    )

    # Public sharing is opt-in. The opaque token keeps public URLs
    # separate from sequential database IDs.
    share_token = db.Column(
        db.String(64),
        unique=True,
        nullable=True,
        index=True,
    )

    is_public = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.false(),
    )

    # Optional manual transport into the first stop.
    arrival_transport_mode = db.Column(
        db.String(20),
        nullable=True,
    )

    arrival_transport_cost_gbp = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        default=0,
        server_default="0",
    )

    arrival_transport_note = db.Column(
        db.String(200),
        nullable=True,
    )

    # Optional manual transport away from the final stop.
    departure_transport_mode = db.Column(
        db.String(20),
        nullable=True,
    )

    departure_transport_cost_gbp = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        default=0,
        server_default="0",
    )

    departure_transport_note = db.Column(
        db.String(200),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "trips",
            lazy=True,
        ),
    )

    stops = db.relationship(
        "TripStop",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripStop.position",
        lazy=True,
    )

    legs = db.relationship(
        "TripLeg",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripLeg.position",
        lazy=True,
    )

    @property
    def total_nights(self):
        return sum(stop.nights for stop in self.stops)

    @property
    def stay_cost_gbp(self):
        return round(
            sum(stop.total_cost_gbp for stop in self.stops),
            2,
        )

    @property
    def intercity_transport_cost_gbp(self):
        return round(
            sum(float(leg.cost_gbp or 0) for leg in self.legs),
            2,
        )

    @property
    def transport_cost_gbp(self):
        return round(
            float(self.arrival_transport_cost_gbp or 0)
            + self.intercity_transport_cost_gbp
            + float(self.departure_transport_cost_gbp or 0),
            2,
        )

    @property
    def total_cost_gbp(self):
        return round(
            self.stay_cost_gbp + self.transport_cost_gbp,
            2,
        )

    @property
    def accommodation_cost_gbp(self):
        return round(
            sum(stop.accommodation_cost_gbp for stop in self.stops),
            2,
        )

    @property
    def living_cost_gbp(self):
        return round(
            sum(stop.living_cost_gbp for stop in self.stops),
            2,
        )

    @property
    def average_cost_gbp(self):
        """
        Average daily stay cost.

        Transport is intentionally excluded because buses, trains and flights
        are one-off trip costs. They still remain part of total_cost_gbp.
        """
        if not self.total_nights:
            return 0

        return round(
            self.stay_cost_gbp / self.total_nights,
            2,
        )

    @property
    def schengen_nights(self):
        return sum(
            stop.nights
            for stop in self.stops
            if stop.city.country.is_schengen
        )

    @property
    def non_schengen_nights(self):
        return self.total_nights - self.schengen_nights

    def convert_from_gbp(self, value):
        return round(
            float(value) * float(self.fx_rate),
            2,
        )

    @property
    def total_cost_display(self):
        return self.convert_from_gbp(self.total_cost_gbp)

    @property
    def average_cost_display(self):
        return self.convert_from_gbp(self.average_cost_gbp)

    @property
    def stay_cost_display(self):
        return self.convert_from_gbp(self.stay_cost_gbp)

    @property
    def transport_cost_display(self):
        return self.convert_from_gbp(self.transport_cost_gbp)


class TripStop(db.Model):
    __tablename__ = "trip_stop"

    id = db.Column(db.Integer, primary_key=True)

    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trip.id"),
        nullable=False,
        index=True,
    )

    city_id = db.Column(
        db.Integer,
        db.ForeignKey("city.id"),
        nullable=False,
        index=True,
    )

    position = db.Column(
        db.Integer,
        nullable=False,
    )

    nights = db.Column(
        db.Integer,
        nullable=False,
    )

    # Snapshot the estimate that the user actually saved.
    # Source values stay canonical in GBP.
    daily_cost_gbp = db.Column(
        db.Numeric(10, 2),
        nullable=False,
    )

    hostel_per_night_gbp = db.Column(
        db.Numeric(10, 2),
        nullable=False,
    )

    living_per_day_gbp = db.Column(
        db.Numeric(10, 2),
        nullable=False,
    )

    trip = db.relationship(
        "Trip",
        back_populates="stops",
    )

    city = db.relationship(
        "City",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "trip_id",
            "position",
            name="uq_trip_stop_position",
        ),
    )

    @property
    def total_cost_gbp(self):
        return round(
            float(self.daily_cost_gbp) * self.nights,
            2,
        )

    @property
    def accommodation_cost_gbp(self):
        return round(
            float(self.hostel_per_night_gbp) * self.nights,
            2,
        )

    @property
    def living_cost_gbp(self):
        return round(
            float(self.living_per_day_gbp) * self.nights,
            2,
        )



class TripLeg(db.Model):
    __tablename__ = "trip_leg"

    id = db.Column(db.Integer, primary_key=True)

    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trip.id"),
        nullable=False,
        index=True,
    )

    from_city_id = db.Column(
        db.Integer,
        db.ForeignKey("city.id"),
        nullable=False,
        index=True,
    )

    to_city_id = db.Column(
        db.Integer,
        db.ForeignKey("city.id"),
        nullable=False,
        index=True,
    )

    position = db.Column(
        db.Integer,
        nullable=False,
    )

    mode = db.Column(
        db.String(20),
        nullable=True,
    )

    cost_gbp = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        default=0,
        server_default="0",
    )

    note = db.Column(
        db.String(200),
        nullable=True,
    )

    trip = db.relationship(
        "Trip",
        back_populates="legs",
    )

    from_city = db.relationship(
        "City",
        foreign_keys=[from_city_id],
    )

    to_city = db.relationship(
        "City",
        foreign_keys=[to_city_id],
    )

    __table_args__ = (
        db.UniqueConstraint(
            "trip_id",
            "position",
            name="uq_trip_leg_position",
        ),
    )
