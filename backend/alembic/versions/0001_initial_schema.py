"""Initial relational schema migration for rost_crm.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-09-22 21:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
        is_offline = False
    except Exception:
        existing_tables = set()
        is_offline = True

    def table_missing(name: str) -> bool:
        if is_offline:
            return True
        return name not in existing_tables

    def column_missing(table_name: str, col_name: str) -> bool:
        if is_offline or table_missing(table_name):
            return True
        cols = {c["name"] for c in inspector.get_columns(table_name)}
        return col_name not in cols

    # 1. Independent lookup and core entity tables
    if table_missing("directions"):
        op.create_table(
            "directions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if table_missing("products"):
        op.create_table(
            "products",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("vendor", sa.String(length=200), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if table_missing("teams"):
        op.create_table(
            "teams",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if table_missing("workflow_versions"):
        op.create_table(
            "workflow_versions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("definition", sa.JSON(), nullable=True),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("version"),
        )
    else:
        if column_missing("workflow_versions", "definition"):
            op.add_column("workflow_versions", sa.Column("definition", sa.JSON(), nullable=True))
        if column_missing("workflow_versions", "is_published"):
            op.add_column("workflow_versions", sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    if table_missing("workflow_migration_dry_runs"):
        op.create_table(
            "workflow_migration_dry_runs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("from_version", sa.Integer(), nullable=False),
            sa.Column("to_version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # 1.5 Users (depends on teams)
    if table_missing("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("keycloak_subject", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("team_id", sa.String(length=64), nullable=True),
            sa.Column("permissions", sa.JSON(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("keycloak_subject"),
        )

    # 1.6 Organizations (depends on users)
    if table_missing("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=250), nullable=False),
            sa.Column("type", sa.String(length=32), nullable=False),
            sa.Column("owner_id", sa.String(length=64), nullable=True),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("organizations", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_organizations_owner_id"), ["owner_id"], unique=False)
    else:
        if column_missing("organizations", "owner_id"):
            op.add_column("organizations", sa.Column("owner_id", sa.String(length=64), nullable=True))

    # 2. Tables dependent on organizations, directions, teams
    if table_missing("contracts"):
        op.create_table(
            "contracts",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("number", sa.String(length=100), nullable=False),
            sa.Column("signed_on", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("contracts", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_contracts_organization_id"), ["organization_id"], unique=False)

    if table_missing("organization_contacts"):
        op.create_table(
            "organization_contacts",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("full_name", sa.String(length=250), nullable=False),
            sa.Column("position", sa.String(length=200), nullable=False),
            sa.Column("email", sa.String(length=200), nullable=True),
            sa.Column("phone", sa.String(length=100), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("organization_contacts", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_organization_contacts_organization_id"), ["organization_id"], unique=False)

    if table_missing("programs"):
        op.create_table(
            "programs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("direction_id", sa.String(length=64), nullable=False),
            sa.ForeignKeyConstraint(["direction_id"], ["directions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    # 3. Tables dependent on users, programs, products, contracts
    if table_missing("command_results"):
        op.create_table(
            "command_results",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("operation", sa.String(length=200), nullable=False),
            sa.Column("key", sa.String(length=200), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("response", sa.JSON(), nullable=True),
            sa.Column("resource_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "operation", "key", name="uq_command_key"),
        )

    if table_missing("learning_metrics"):
        op.create_table(
            "learning_metrics",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("program_id", sa.String(length=64), nullable=False),
            sa.Column("metric_code", sa.String(length=64), nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(length=32), nullable=False),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("external_id", sa.String(length=128), nullable=False),
            sa.Column("last_applied_revision", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["program_id"], ["programs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "external_id", name="uq_learning_metric_source_external"),
        )
        with op.batch_alter_table("learning_metrics", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_learning_metrics_organization_id"), ["organization_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_learning_metrics_program_id"), ["program_id"], unique=False)
            batch_op.create_index("ix_metric_code_as_of", ["metric_code", "as_of"], unique=False)
            batch_op.create_index("ix_metric_org_prog", ["organization_id", "program_id"], unique=False)
    else:
        if column_missing("learning_metrics", "last_applied_revision"):
            op.add_column("learning_metrics", sa.Column("last_applied_revision", sa.String(length=64), nullable=True))

    if table_missing("licenses"):
        op.create_table(
            "licenses",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("product_id", sa.String(length=64), nullable=False),
            sa.Column("contract_id", sa.String(length=64), nullable=True),
            sa.Column("signed_on", sa.DateTime(timezone=True), nullable=True),
            sa.Column("term_years", sa.Integer(), nullable=True),
            sa.Column("transfer_status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("licenses", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_licenses_contract_id"), ["contract_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_licenses_organization_id"), ["organization_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_licenses_product_id"), ["product_id"], unique=False)

    if table_missing("organization_access"):
        op.create_table(
            "organization_access",
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("can_create", sa.Boolean(), nullable=False),
            sa.Column("read_all", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("user_id", "organization_id"),
        )

    if table_missing("program_products"):
        op.create_table(
            "program_products",
            sa.Column("program_id", sa.String(length=64), nullable=False),
            sa.Column("product_id", sa.String(length=64), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["program_id"], ["programs.id"]),
            sa.PrimaryKeyConstraint("program_id", "product_id"),
        )

    # 4. Interactions
    if table_missing("interactions"):
        op.create_table(
            "interactions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=250), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("program_id", sa.String(length=64), nullable=True),
            sa.Column("product_id", sa.String(length=64), nullable=True),
            sa.Column("cycle_label", sa.String(length=100), nullable=False),
            sa.Column("owner_id", sa.String(length=64), nullable=False),
            sa.Column("contract_id", sa.String(length=64), nullable=True),
            sa.Column("license_id", sa.String(length=64), nullable=True),
            sa.Column("contact_id", sa.String(length=64), nullable=True),
            sa.Column("team_id", sa.String(length=64), nullable=True),
            sa.Column("state", sa.String(length=80), nullable=False),
            sa.Column("workflow_version", sa.Integer(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("visit_id", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["contact_id"], ["organization_contacts.id"]),
            sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
            sa.ForeignKeyConstraint(["license_id"], ["licenses.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["program_id"], ["programs.id"]),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("interactions", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_interactions_contact_id"), ["contact_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_interactions_contract_id"), ["contract_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_interactions_license_id"), ["license_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_interactions_organization_id"), ["organization_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_interactions_owner_id"), ["owner_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_interactions_team_id"), ["team_id"], unique=False)

    # 5. Tables dependent on interactions
    if table_missing("attachments"):
        op.create_table(
            "attachments",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("interaction_id", sa.String(length=64), nullable=False),
            sa.Column("visit_id", sa.String(length=64), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("file_path", sa.String(length=500), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("checksum", sa.String(length=64), nullable=False),
            sa.Column("uploaded_by", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"]),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("attachments", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_attachments_interaction_id"), ["interaction_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_attachments_visit_id"), ["visit_id"], unique=False)

    if table_missing("comments"):
        op.create_table(
            "comments",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("interaction_id", sa.String(length=64), nullable=False),
            sa.Column("author_id", sa.String(length=64), nullable=False),
            sa.Column("author_name", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("visit_id", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("comments", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_comments_interaction_id"), ["interaction_id"], unique=False)

    if table_missing("deliveries"):
        op.create_table(
            "deliveries",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("organization_id", sa.String(length=64), nullable=False),
            sa.Column("interaction_id", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("channel", sa.String(length=40), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("recipient_contact_id", sa.String(length=64), nullable=True),
            sa.Column("recorded_by", sa.String(length=64), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["recipient_contact_id"], ["organization_contacts.id"]),
            sa.ForeignKeyConstraint(["recorded_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("deliveries", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_deliveries_interaction_id"), ["interaction_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_deliveries_organization_id"), ["organization_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_deliveries_recorded_by"), ["recorded_by"], unique=False)

    if table_missing("integration_inbox"):
        op.create_table(
            "integration_inbox",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("external_id", sa.String(length=128), nullable=False),
            sa.Column("source_revision", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("matched_organization_id", sa.String(length=64), nullable=True),
            sa.Column("matched_interaction_id", sa.String(length=64), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["matched_interaction_id"], ["interactions.id"]),
            sa.ForeignKeyConstraint(["matched_organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "entity_type", "external_id", "source_revision", name="uq_inbox_dedup"),
        )
        with op.batch_alter_table("integration_inbox", schema=None) as batch_op:
            batch_op.create_index("ix_inbox_received_at", ["received_at"], unique=False)
            batch_op.create_index("ix_inbox_source_status", ["source", "status"], unique=False)
            batch_op.create_index(batch_op.f("ix_integration_inbox_entity_type"), ["entity_type"], unique=False)
            batch_op.create_index(batch_op.f("ix_integration_inbox_external_id"), ["external_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_integration_inbox_matched_interaction_id"), ["matched_interaction_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_integration_inbox_matched_organization_id"), ["matched_organization_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_integration_inbox_received_at"), ["received_at"], unique=False)
            batch_op.create_index(batch_op.f("ix_integration_inbox_source"), ["source"], unique=False)
            batch_op.create_index(batch_op.f("ix_integration_inbox_status"), ["status"], unique=False)

    if table_missing("interaction_events"):
        op.create_table(
            "interaction_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("interaction_id", sa.String(length=64), nullable=False),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.String(length=64), nullable=False),
            sa.Column("actor_name", sa.String(length=200), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("interaction_id", "sequence", name="uq_event_sequence"),
        )
        with op.batch_alter_table("interaction_events", schema=None) as batch_op:
            batch_op.create_index("ix_event_temporal", ["interaction_id", "effective_at", "received_at"], unique=False)
            batch_op.create_index(batch_op.f("ix_interaction_events_interaction_id"), ["interaction_id"], unique=False)

    # 6. Delivery items (depends on deliveries, attachments, licenses)
    if table_missing("delivery_items"):
        op.create_table(
            "delivery_items",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("delivery_id", sa.String(length=64), nullable=False),
            sa.Column("item_kind", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=250), nullable=False),
            sa.Column("attachment_id", sa.String(length=64), nullable=True),
            sa.Column("license_id", sa.String(length=64), nullable=True),
            sa.Column("material_version", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["attachment_id"], ["attachments.id"]),
            sa.ForeignKeyConstraint(["delivery_id"], ["deliveries.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["license_id"], ["licenses.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("delivery_items", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_delivery_items_delivery_id"), ["delivery_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
        is_offline = False
    except Exception:
        existing_tables = set()
        is_offline = True

    def table_exists(name: str) -> bool:
        if is_offline:
            return True
        return name in existing_tables

    # Drop in exact reverse topological order of dependencies
    if table_exists("delivery_items"):
        with op.batch_alter_table("delivery_items", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_delivery_items_delivery_id"))
        op.drop_table("delivery_items")

    if table_exists("interaction_events"):
        with op.batch_alter_table("interaction_events", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_interaction_events_interaction_id"))
            batch_op.drop_index("ix_event_temporal")
        op.drop_table("interaction_events")

    if table_exists("integration_inbox"):
        with op.batch_alter_table("integration_inbox", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_integration_inbox_status"))
            batch_op.drop_index(batch_op.f("ix_integration_inbox_source"))
            batch_op.drop_index(batch_op.f("ix_integration_inbox_received_at"))
            batch_op.drop_index(batch_op.f("ix_integration_inbox_matched_organization_id"))
            batch_op.drop_index(batch_op.f("ix_integration_inbox_matched_interaction_id"))
            batch_op.drop_index(batch_op.f("ix_integration_inbox_external_id"))
            batch_op.drop_index(batch_op.f("ix_integration_inbox_entity_type"))
            batch_op.drop_index("ix_inbox_source_status")
            batch_op.drop_index("ix_inbox_received_at")
        op.drop_table("integration_inbox")

    if table_exists("deliveries"):
        with op.batch_alter_table("deliveries", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_deliveries_recorded_by"))
            batch_op.drop_index(batch_op.f("ix_deliveries_organization_id"))
            batch_op.drop_index(batch_op.f("ix_deliveries_interaction_id"))
        op.drop_table("deliveries")

    if table_exists("comments"):
        with op.batch_alter_table("comments", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_comments_interaction_id"))
        op.drop_table("comments")

    if table_exists("attachments"):
        with op.batch_alter_table("attachments", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_attachments_visit_id"))
            batch_op.drop_index(batch_op.f("ix_attachments_interaction_id"))
        op.drop_table("attachments")

    if table_exists("interactions"):
        with op.batch_alter_table("interactions", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_interactions_team_id"))
            batch_op.drop_index(batch_op.f("ix_interactions_owner_id"))
            batch_op.drop_index(batch_op.f("ix_interactions_organization_id"))
            batch_op.drop_index(batch_op.f("ix_interactions_license_id"))
            batch_op.drop_index(batch_op.f("ix_interactions_contract_id"))
            batch_op.drop_index(batch_op.f("ix_interactions_contact_id"))
        op.drop_table("interactions")

    if table_exists("program_products"):
        op.drop_table("program_products")

    if table_exists("organization_access"):
        op.drop_table("organization_access")

    if table_exists("licenses"):
        with op.batch_alter_table("licenses", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_licenses_product_id"))
            batch_op.drop_index(batch_op.f("ix_licenses_organization_id"))
            batch_op.drop_index(batch_op.f("ix_licenses_contract_id"))
        op.drop_table("licenses")

    if table_exists("learning_metrics"):
        with op.batch_alter_table("learning_metrics", schema=None) as batch_op:
            batch_op.drop_index("ix_metric_org_prog")
            batch_op.drop_index("ix_metric_code_as_of")
            batch_op.drop_index(batch_op.f("ix_learning_metrics_program_id"))
            batch_op.drop_index(batch_op.f("ix_learning_metrics_organization_id"))
        op.drop_table("learning_metrics")

    if table_exists("organization_contacts"):
        with op.batch_alter_table("organization_contacts", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_organization_contacts_organization_id"))
        op.drop_table("organization_contacts")

    if table_exists("contracts"):
        with op.batch_alter_table("contracts", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_contracts_organization_id"))
        op.drop_table("contracts")

    if table_exists("organizations"):
        with op.batch_alter_table("organizations", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_organizations_owner_id"))
        op.drop_table("organizations")

    if table_exists("command_results"):
        op.drop_table("command_results")

    if table_exists("users"):
        op.drop_table("users")

    if table_exists("programs"):
        op.drop_table("programs")

    if table_exists("workflow_migration_dry_runs"):
        op.drop_table("workflow_migration_dry_runs")

    if table_exists("workflow_versions"):
        op.drop_table("workflow_versions")

    if table_exists("teams"):
        op.drop_table("teams")

    if table_exists("products"):
        op.drop_table("products")

    if table_exists("directions"):
        op.drop_table("directions")
