"""Temporal fact tables for state visits and frozen report runs (TASK-O03).

Revision ID: 0004_temporal_fact_tables
Revises: 0003_authz_epoch
Create Date: 2026-09-23 20:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_temporal_fact_tables"
down_revision: Union[str, None] = "0003_authz_epoch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "state_visits",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("interaction_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=80), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("state_visits", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_state_visits_interaction_id"), ["interaction_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_state_visits_state"), ["state"], unique=False)

    op.create_table(
        "report_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("parameters_hash", sa.String(length=64), nullable=False),
        sa.Column("knowledge_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("dataset_checksum", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("report_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_report_runs_parameters_hash"), ["parameters_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_report_runs_requested_by"), ["requested_by"], unique=False)

    op.create_table(
        "report_rows",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("report_run_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("row_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("report_rows", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_report_rows_report_run_id"), ["report_run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("report_rows", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_report_rows_report_run_id"))
    op.drop_table("report_rows")

    with op.batch_alter_table("report_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_report_runs_requested_by"))
        batch_op.drop_index(batch_op.f("ix_report_runs_parameters_hash"))
    op.drop_table("report_runs")

    with op.batch_alter_table("state_visits", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_state_visits_state"))
        batch_op.drop_index(batch_op.f("ix_state_visits_interaction_id"))
    op.drop_table("state_visits")
