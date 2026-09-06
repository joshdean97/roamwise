"""add explore, points and trip attribution

Revision ID: f8d3c1a5e204
Revises: e6c2b9d4f731
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa


revision = "f8d3c1a5e204"
down_revision = "e6c2b9d4f731"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("trip", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_trip_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_trip_source_trip_id",
            ["source_trip_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_trip_source_trip_id_trip",
            "trip",
            ["source_trip_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "trip_engagement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('save', 'use')",
            name="ck_trip_engagement_kind",
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "trip_id",
            "kind",
            name="uq_trip_engagement_user_trip_kind",
        ),
    )
    op.create_index(
        "ix_trip_engagement_user_id",
        "trip_engagement",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_trip_engagement_trip_id",
        "trip_engagement",
        ["trip_id"],
        unique=False,
    )
    op.create_index(
        "ix_trip_engagement_kind",
        "trip_engagement",
        ["kind"],
        unique=False,
    )
    op.create_index(
        "ix_trip_engagement_created_at",
        "trip_engagement",
        ["created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_trip_engagement_created_at", table_name="trip_engagement")
    op.drop_index("ix_trip_engagement_kind", table_name="trip_engagement")
    op.drop_index("ix_trip_engagement_trip_id", table_name="trip_engagement")
    op.drop_index("ix_trip_engagement_user_id", table_name="trip_engagement")
    op.drop_table("trip_engagement")

    with op.batch_alter_table("trip", schema=None) as batch_op:
        batch_op.drop_constraint("fk_trip_source_trip_id_trip", type_="foreignkey")
        batch_op.drop_index("ix_trip_source_trip_id")
        batch_op.drop_column("source_trip_id")
