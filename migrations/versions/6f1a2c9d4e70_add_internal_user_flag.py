"""add internal analytics flag and price verification metadata

Revision ID: 6f1a2c9d4e70
Revises: e9b4c6d2a710
Create Date: 2026-09-22

"""
from alembic import op
import sqlalchemy as sa


revision = "6f1a2c9d4e70"
down_revision = "e9b4c6d2a710"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "is_internal",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    # Backfill the known classes of non-customer accounts. Future dedicated
    # test accounts can be marked explicitly without relying on their email.
    op.execute(
        sa.text(
            'UPDATE "user" '
            "SET is_internal = true "
            "WHERE is_admin = true OR lower(email) LIKE '%@test.com'"
        )
    )

    op.add_column("city", sa.Column("price_checked_at", sa.DateTime(), nullable=True))
    op.add_column("city", sa.Column("price_source", sa.String(length=255), nullable=True))
    op.add_column(
        "city",
        sa.Column(
            "price_confidence",
            sa.String(length=20),
            server_default="unverified",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_city_price_checked_at",
        "city",
        ["price_checked_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_city_price_checked_at", table_name="city")
    op.drop_column("city", "price_confidence")
    op.drop_column("city", "price_source")
    op.drop_column("city", "price_checked_at")
    op.drop_column("user", "is_internal")
