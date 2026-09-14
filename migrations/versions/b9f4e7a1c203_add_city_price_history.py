"""add immutable city price history

Revision ID: b9f4e7a1c203
Revises: a4d9e7f2c610
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "b9f4e7a1c203"
down_revision = "a4d9e7f2c610"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "city_price_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("hostel_per_night", sa.Numeric(10, 2), nullable=False),
        sa.Column("monthly_living_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("balanced_daily_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default="admin_update",
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["city_id"], ["city.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_city_price_snapshot_city_id",
        "city_price_snapshot",
        ["city_id"],
        unique=False,
    )
    op.create_index(
        "ix_city_price_snapshot_recorded_at",
        "city_price_snapshot",
        ["recorded_at"],
        unique=False,
    )

    # Preserve the current catalogue as the historical baseline. Future admin
    # price edits append a new immutable row.
    op.execute(
        """
        INSERT INTO city_price_snapshot
            (city_id, hostel_per_night, monthly_living_cost,
             balanced_daily_cost, source)
        SELECT
            id,
            hostel_per_night,
            monthly_living_cost,
            ROUND(
                ((hostel_per_night * 30) + monthly_living_cost + 100) / 30,
                2
            ),
            'migration_baseline'
        FROM city
        """
    )


def downgrade():
    op.drop_index(
        "ix_city_price_snapshot_recorded_at",
        table_name="city_price_snapshot",
    )
    op.drop_index(
        "ix_city_price_snapshot_city_id",
        table_name="city_price_snapshot",
    )
    op.drop_table("city_price_snapshot")
