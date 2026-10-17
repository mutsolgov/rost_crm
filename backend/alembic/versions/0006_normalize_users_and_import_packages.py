"""Normalize users email column and create import_packages table.

Revision ID: 0006_normalize_users_and_import_packages
Revises: 0005_background_jobs_and_outbox
Create Date: 2026-10-14 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_normalize_users_and_import_packages"
down_revision: Union[str, None] = "0005_background_jobs_and_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Ensure alembic_version version_num column can hold revision IDs longer than 32 chars
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        op.alter_column("alembic_version", "version_num", type_=sa.String(64), existing_type=sa.String(32))

    # 1. Add email column to users
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=False)

    # 2. Create import_packages table
    op.create_table(
        "import_packages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("import_type", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("rows_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("import_packages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_import_packages_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_import_packages_payload_hash"), ["payload_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_import_packages_expires_at"), ["expires_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("import_packages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_import_packages_expires_at"))
        batch_op.drop_index(batch_op.f("ix_import_packages_payload_hash"))
        batch_op.drop_index(batch_op.f("ix_import_packages_user_id"))
    op.drop_table("import_packages")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_email"))
        batch_op.drop_column("email")
