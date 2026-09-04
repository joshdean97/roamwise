"""Add base user/country/city schema

Revision ID: 714cd86adc94
Revises:
Create Date: 2026-09-01 14:03:17.408257

This project originally began using Alembic after these base tables already
existed in local SQLite. Before the first public deployment, this historical
revision was repaired so a completely fresh production database can migrate
from zero.
"""
from alembic import op
import sqlalchemy as sa


revision = "714cd86adc94"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "country",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=2), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("is_schengen", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "city",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("hostel_per_night", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("monthly_living_cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("last_updated", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["country_id"], ["country.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "country_id", name="uq_city_country"),
    )
    op.create_index("ix_city_country_id", "city", ["country_id"], unique=False)


def downgrade():
    op.drop_index("ix_city_country_id", table_name="city")
    op.drop_table("city")
    op.drop_table("country")
    op.drop_table("user")
