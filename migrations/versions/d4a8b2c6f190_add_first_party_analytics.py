"""add first party analytics events

Revision ID: d4a8b2c6f190
Revises: c3f7a0d1e5b2
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa


revision = "d4a8b2c6f190"
down_revision = "c3f7a0d1e5b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analytics_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analytics_event_name",
        "analytics_event",
        ["name"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_event_user_id",
        "analytics_event",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_event_created_at",
        "analytics_event",
        ["created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_analytics_event_created_at", table_name="analytics_event")
    op.drop_index("ix_analytics_event_user_id", table_name="analytics_event")
    op.drop_index("ix_analytics_event_name", table_name="analytics_event")
    op.drop_table("analytics_event")
