"""add onboarding email delivery

Revision ID: a4d9e7f2c610
Revises: f8d3c1a5e204
"""

from alembic import op
import sqlalchemy as sa


revision = "a4d9e7f2c610"
down_revision = "f8d3c1a5e204"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "user",
        sa.Column("onboarding_email_claimed_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "user",
        sa.Column("onboarding_email_sent_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        sa.text(
            'UPDATE "user" '
            "SET created_at = COALESCE(terms_accepted_at, email_confirmed_at, CURRENT_TIMESTAMP)"
        )
    )
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
    op.create_index("ix_user_created_at", "user", ["created_at"])
    op.create_index(
        "ix_user_onboarding_email_sent_at",
        "user",
        ["onboarding_email_sent_at"],
    )


def downgrade():
    op.drop_index("ix_user_onboarding_email_sent_at", table_name="user")
    op.drop_index("ix_user_created_at", table_name="user")
    op.drop_column("user", "onboarding_email_sent_at")
    op.drop_column("user", "onboarding_email_claimed_at")
    op.drop_column("user", "created_at")
