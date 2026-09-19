"""add rendered content draft review queue

Revision ID: e9b4c6d2a710
Revises: c7a1f4e8d209
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa


revision = "e9b4c6d2a710"
down_revision = "c7a1f4e8d209"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_draft",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("batch_key", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
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
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="ready",
            nullable=False,
        ),
        sa.Column("headline", sa.String(length=500), nullable=True),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("overlay_text", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("pexels_video_id", sa.String(length=64), nullable=True),
        sa.Column("pexels_page_url", sa.String(length=1000), nullable=True),
        sa.Column("pexels_attribution", sa.String(length=255), nullable=True),
        sa.Column("render_id", sa.String(length=255), nullable=False),
        sa.Column("render_url", sa.String(length=1000), nullable=False),
        sa.Column("snapshot_url", sa.String(length=1000), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_key",
            "position",
            name="uq_content_draft_batch_position",
        ),
        sa.UniqueConstraint("render_id"),
    )
    op.create_index("ix_content_draft_trip_id", "content_draft", ["trip_id"])
    op.create_index("ix_content_draft_batch_key", "content_draft", ["batch_key"])
    op.create_index("ix_content_draft_platform", "content_draft", ["platform"])
    op.create_index("ix_content_draft_format", "content_draft", ["format"])
    op.create_index("ix_content_draft_status", "content_draft", ["status"])
    op.create_index("ix_content_draft_render_id", "content_draft", ["render_id"])
    op.create_index("ix_content_draft_posted_at", "content_draft", ["posted_at"])
    op.create_index("ix_content_draft_created_at", "content_draft", ["created_at"])
    op.create_index(
        "ix_content_draft_trip_platform_format_status",
        "content_draft",
        ["trip_id", "platform", "format", "status"],
    )


def downgrade():
    op.drop_index(
        "ix_content_draft_trip_platform_format_status",
        table_name="content_draft",
    )
    op.drop_index("ix_content_draft_created_at", table_name="content_draft")
    op.drop_index("ix_content_draft_posted_at", table_name="content_draft")
    op.drop_index("ix_content_draft_render_id", table_name="content_draft")
    op.drop_index("ix_content_draft_status", table_name="content_draft")
    op.drop_index("ix_content_draft_format", table_name="content_draft")
    op.drop_index("ix_content_draft_platform", table_name="content_draft")
    op.drop_index("ix_content_draft_batch_key", table_name="content_draft")
    op.drop_index("ix_content_draft_trip_id", table_name="content_draft")
    op.drop_table("content_draft")
