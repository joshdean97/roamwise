from core.extensions import db


class Country(db.Model):
    __tablename__ = "country"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    code = db.Column(
        db.String(2),
        unique=True,
        nullable=False
    )

    currency_code = db.Column(
        db.String(3),
        nullable=False
    )

    is_schengen = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    visa_buffer = db.Column(
        db.Boolean,
        nullable=True,
        default=False
    )

    region = db.Column(
        db.String(100),
        nullable=True
    )

    cities = db.relationship(
        "City",
        back_populates="country",
        lazy=True
    )