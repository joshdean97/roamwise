"""add city data reports

Revision ID: e6c2b9d4f731
Revises: d4a8b2c6f190
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa


revision = "e6c2b9d4f731"
down_revision = "d4a8b2c6f190"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "city_data_report",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("city_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("country_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("hostel_per_night_snapshot", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("monthly_living_cost_snapshot", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("balanced_daily_snapshot", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("resolution_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["city_id"], ["city.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_city_data_report_city_id"), "city_data_report", ["city_id"], unique=False)
    op.create_index(op.f("ix_city_data_report_user_id"), "city_data_report", ["user_id"], unique=False)
    op.create_index(op.f("ix_city_data_report_status"), "city_data_report", ["status"], unique=False)
    op.create_index(op.f("ix_city_data_report_created_at"), "city_data_report", ["created_at"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_city_data_report_created_at"), table_name="city_data_report")
    op.drop_index(op.f("ix_city_data_report_status"), table_name="city_data_report")
    op.drop_index(op.f("ix_city_data_report_user_id"), table_name="city_data_report")
    op.drop_index(op.f("ix_city_data_report_city_id"), table_name="city_data_report")
    op.drop_table("city_data_report")
