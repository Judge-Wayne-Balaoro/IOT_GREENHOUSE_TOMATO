"""add manual growth measurements and separate ultrasonic tests

Revision ID: 91b6e8f3a2d1
Revises: 8ae04c4d6063
Create Date: 2026-10-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "91b6e8f3a2d1"
down_revision: Union[str, Sequence[str], None] = "8ae04c4d6063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_growth_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_manual_growth_plant_recorded", "manual_growth_measurements", ["plant_id", "recorded_at"])
    op.create_table(
        "ultrasonic_tests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distance_cm", sa.Float(), nullable=True),
        sa.Column("estimated_height_cm", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_ultrasonic_plant_recorded", "ultrasonic_tests", ["plant_id", "recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_ultrasonic_plant_recorded", table_name="ultrasonic_tests")
    op.drop_table("ultrasonic_tests")
    op.drop_index("ix_manual_growth_plant_recorded", table_name="manual_growth_measurements")
    op.drop_table("manual_growth_measurements")
