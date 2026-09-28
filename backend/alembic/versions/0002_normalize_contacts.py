"""Normalize organization contacts schema (TASK-P05).

Revision ID: 0002_normalize_contacts
Revises: 0001_initial_schema
Create Date: 2026-09-23 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_normalize_contacts"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("organization_contacts", schema=None) as batch_op:
        batch_op.alter_column(
            "email",
            existing_type=sa.String(length=200),
            type_=sa.String(length=320),
            existing_nullable=True,
        )
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False))
        batch_op.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_org_contacts_active", ["organization_id", "archived_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("organization_contacts", schema=None) as batch_op:
        batch_op.drop_index("ix_org_contacts_active")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("revision")
        batch_op.drop_column("notes")
        batch_op.alter_column(
            "email",
            existing_type=sa.String(length=320),
            type_=sa.String(length=200),
            existing_nullable=True,
        )
