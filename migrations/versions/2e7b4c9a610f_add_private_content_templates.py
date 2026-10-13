"""Explicitly opt curated private trips into the content generator."""
from alembic import op
import sqlalchemy as sa

revision = "2e7b4c9a610f"
down_revision = "6f1a2c9d4e70"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("trip", sa.Column("is_content_template", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("trip", sa.Column("content_source_key", sa.String(100), nullable=True))
    op.add_column("trip", sa.Column("content_research", sa.JSON(), nullable=True))
    op.create_index("uq_trip_content_source_key", "trip", ["content_source_key"], unique=True)


def downgrade():
    op.drop_index("uq_trip_content_source_key", table_name="trip")
    op.drop_column("trip", "content_research")
    op.drop_column("trip", "content_source_key")
    op.drop_column("trip", "is_content_template")
