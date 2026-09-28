from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def new_id():
    return str(uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    keycloak_subject: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32))
    team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def email(self) -> str | None:
        if self.keycloak_subject and "@" in self.keycloak_subject:
            return self.keycloak_subject
        return getattr(self, "_email", None)

    @email.setter
    def email(self, val: str | None) -> None:
        self._email = val
        if val and "@" in val:
            if not getattr(self, "keycloak_subject", None) or "@" in (self.keycloak_subject or ""):
                self.keycloak_subject = val

    @property
    def phone(self) -> str | None:
        if hasattr(self, "_phone") and self._phone:
            return self._phone
        if isinstance(self.permissions, list):
            for item in self.permissions:
                if isinstance(item, str) and item.startswith("phone:"):
                    return item.split(":", 1)[1]
                if isinstance(item, dict) and "phone" in item:
                    return item["phone"]
        return getattr(self, "_phone", None)

    @phone.setter
    def phone(self, val: str | None) -> None:
        self._phone = val
        if val:
            perms = list(self.permissions or [])
            new_perms = [
                p for p in perms
                if not (isinstance(p, str) and p.startswith("phone:"))
                and not (isinstance(p, dict) and "phone" in p)
            ]
            new_perms.append(f"phone:{val}")
            self.permissions = new_perms
        else:
            if self.permissions:
                self.permissions = [
                    p for p in self.permissions
                    if not (isinstance(p, str) and p.startswith("phone:"))
                    and not (isinstance(p, dict) and "phone" in p)
                ]



class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(250))
    type: Mapped[str] = mapped_column(String(32), default="university")
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, default=None)


class OrganizationAccess(Base):
    __tablename__ = "organization_access"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    can_create: Mapped[bool] = mapped_column(Boolean, default=False)
    read_all: Mapped[bool] = mapped_column(Boolean, default=False)


class Direction(Base):
    __tablename__ = "directions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class Program(Base):
    __tablename__ = "programs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    direction_id: Mapped[str] = mapped_column(ForeignKey("directions.id"))


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    vendor: Mapped[str] = mapped_column(String(200))


class ProgramProduct(Base):
    __tablename__ = "program_products"
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), primary_key=True)


class OrganizationContact(Base):
    __tablename__ = "organization_contacts"
    __table_args__ = (
        Index("ix_org_contacts_active", "organization_id", "archived_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(250))
    position: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    number: Mapped[str] = mapped_column(String(100))
    signed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class License(Base):
    __tablename__ = "licenses"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"), index=True, nullable=True)
    signed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    term_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transfer_status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Interaction(Base):
    __tablename__ = "interactions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(250))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    program_id: Mapped[str | None] = mapped_column(ForeignKey("programs.id"), nullable=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    cycle_label: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"), index=True, nullable=True)
    license_id: Mapped[str | None] = mapped_column(ForeignKey("licenses.id"), index=True, nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("organization_contacts.id"), index=True, nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.id", ondelete="SET NULL"), index=True, nullable=True)
    state: Mapped[str] = mapped_column(String(80))
    workflow_version: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    visit_id: Mapped[str] = mapped_column(String(64), default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    interaction_id: Mapped[str] = mapped_column(ForeignKey("interactions.id"), index=True)
    visit_id: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InteractionEvent(Base):
    __tablename__ = "interaction_events"
    __table_args__ = (
        UniqueConstraint("interaction_id", "sequence", name="uq_event_sequence"),
        Index("ix_event_temporal", "interaction_id", "effective_at", "received_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    interaction_id: Mapped[str] = mapped_column(ForeignKey("interactions.id"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sequence: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    interaction_id: Mapped[str] = mapped_column(ForeignKey("interactions.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    author_name: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    visit_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommandResult(Base):
    __tablename__ = "command_results"
    __table_args__ = (UniqueConstraint("user_id", "operation", "key", name="uq_command_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationInbox(Base):
    __tablename__ = "integration_inbox"
    __table_args__ = (
        UniqueConstraint("source", "entity_type", "external_id", "source_revision", name="uq_inbox_dedup"),
        Index("ix_inbox_source_status", "source", "status"),
        Index("ix_inbox_received_at", "received_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    source_revision: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=True)
    matched_interaction_id: Mapped[str | None] = mapped_column(ForeignKey("interactions.id"), index=True, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearningMetric(Base):
    __tablename__ = "learning_metrics"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_learning_metric_source_external"),
        Index("ix_metric_org_prog", "organization_id", "program_id"),
        Index("ix_metric_code_as_of", "metric_code", "as_of"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), index=True)
    metric_code: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32), default="lms")
    external_id: Mapped[str] = mapped_column(String(128))
    last_applied_revision: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    interaction_id: Mapped[str | None] = mapped_column(ForeignKey("interactions.id"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    channel: Mapped[str] = mapped_column(String(40), default="email")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipient_contact_id: Mapped[str | None] = mapped_column(ForeignKey("organization_contacts.id"), nullable=True)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class DeliveryItem(Base):
    __tablename__ = "delivery_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    delivery_id: Mapped[str] = mapped_column(ForeignKey("deliveries.id", ondelete="CASCADE"), index=True)
    item_kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(250))
    attachment_id: Mapped[str | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    license_id: Mapped[str | None] = mapped_column(ForeignKey("licenses.id"), nullable=True)
    material_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowMigrationDryRun(Base):
    __tablename__ = "workflow_migration_dry_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    from_version: Mapped[int] = mapped_column(Integer)
    to_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AccessPolicyState(Base):
    __tablename__ = "access_policy_state"

    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StateVisit(Base):
    __tablename__ = "state_visits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    interaction_id: Mapped[str] = mapped_column(ForeignKey("interactions.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    knowledge_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    dataset_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportRow(Base):
    __tablename__ = "report_rows"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    report_run_id: Mapped[str] = mapped_column(ForeignKey("report_runs.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    row_data: Mapped[dict] = mapped_column(JSON, default=dict)


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    authz_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransactionalOutbox(Base):
    __tablename__ = "transactional_outbox"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

