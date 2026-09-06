from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from core.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    is_admin = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    email_confirmed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    terms_accepted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    terms_version = db.Column(
        db.String(20),
        nullable=True
    )

    @property
    def is_email_confirmed(self):
        return self.email_confirmed_at is not None

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password
        )
