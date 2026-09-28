"""Global access policy state epoch (TASK-O02).

Revision ID: 0003_authz_epoch
Revises: 0002_normalize_contacts
Create Date: 2026-09-23 16:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_authz_epoch"
down_revision: Union[str, None] = "0002_normalize_contacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_policy_state",
        sa.Column("singleton_id", sa.Integer(), nullable=False),
        sa.Column("epoch", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("singleton_id"),
    )
    op.execute("INSERT INTO access_policy_state (singleton_id, epoch) VALUES (1, 1)")


def downgrade() -> None:
    op.drop_table("access_policy_state")
