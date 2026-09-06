"""add terms acceptance audit fields

Revision ID: c3f7a0d1e5b2
Revises: b7e4c1a2d9f0
Create Date: 2026-09-05

"""
from alembic import op
import sqlalchemy as sa


revision = "c3f7a0d1e5b2"
down_revision = "b7e4c1a2d9f0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("terms_version", sa.String(length=20), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("terms_version")
        batch_op.drop_column("terms_accepted_at")
