"""Background jobs and transactional outbox tables (TASK-O01).

Revision ID: 0005_background_jobs_and_outbox
Revises: 0004_temporal_fact_tables
Create Date: 2026-09-24 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_background_jobs_and_outbox"
down_revision: Union[str, None] = "0004_temporal_fact_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.String(length=64), nullable=False),
        sa.Column("authz_epoch", sa.Integer(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("result_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("background_jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_background_jobs_kind"), ["kind"], unique=False)
        batch_op.create_index(batch_op.f("ix_background_jobs_requester_id"), ["requester_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_background_jobs_status"), ["status"], unique=False)

    op.create_table(
        "transactional_outbox",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("transactional_outbox", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_transactional_outbox_event_type"), ["event_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_transactional_outbox_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("transactional_outbox", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_transactional_outbox_status"))
        batch_op.drop_index(batch_op.f("ix_transactional_outbox_event_type"))
    op.drop_table("transactional_outbox")

    with op.batch_alter_table("background_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_background_jobs_status"))
        batch_op.drop_index(batch_op.f("ix_background_jobs_requester_id"))
        batch_op.drop_index(batch_op.f("ix_background_jobs_kind"))
    op.drop_table("background_jobs")
