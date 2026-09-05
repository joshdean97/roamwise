"""add email confirmation

Revision ID: b7e4c1a2d9f0
Revises: faa27366f923
Create Date: 2026-09-05

"""
from alembic import op
import sqlalchemy as sa


revision = "b7e4c1a2d9f0"
down_revision = "faa27366f923"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("email_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )

    # Existing accounts pre-date email confirmation. Grandfather them in so this
    # release does not suddenly lock current users out of LeavePrints.
    op.execute(
        sa.text(
            'UPDATE "user" SET email_confirmed_at = CURRENT_TIMESTAMP '
            'WHERE email_confirmed_at IS NULL'
        )
    )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("email_confirmed_at")
