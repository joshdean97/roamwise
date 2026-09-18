"""add content post tracking

Revision ID: c7a1f4e8d209
Revises: b9f4e7a1c203
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa


revision = "c7a1f4e8d209"
down_revision = "b9f4e7a1c203"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_post",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column(
            "platform",
            sa.String(length=32),
            server_default="instagram",
            nullable=False,
        ),
        sa.Column(
            "format",
            sa.String(length=32),
            server_default="trial_reel",
            nullable=False,
        ),
        sa.Column("hook", sa.String(length=500), nullable=True),
        sa.Column("external_media_id", sa.String(length=255), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_content_post_trip_id",
        "content_post",
        ["trip_id"],
        unique=False,
    )
    op.create_index(
        "ix_content_post_platform",
        "content_post",
        ["platform"],
        unique=False,
    )
    op.create_index(
        "ix_content_post_format",
        "content_post",
        ["format"],
        unique=False,
    )
    op.create_index(
        "ix_content_post_external_media_id",
        "content_post",
        ["external_media_id"],
        unique=False,
    )
    op.create_index(
        "ix_content_post_posted_at",
        "content_post",
        ["posted_at"],
        unique=False,
    )
    op.create_index(
        "ix_content_post_trip_platform_format",
        "content_post",
        ["trip_id", "platform", "format"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_content_post_trip_platform_format",
        table_name="content_post",
    )
    op.drop_index("ix_content_post_posted_at", table_name="content_post")
    op.drop_index(
        "ix_content_post_external_media_id",
        table_name="content_post",
    )
    op.drop_index("ix_content_post_format", table_name="content_post")
    op.drop_index("ix_content_post_platform", table_name="content_post")
    op.drop_index("ix_content_post_trip_id", table_name="content_post")
    op.drop_table("content_post")
