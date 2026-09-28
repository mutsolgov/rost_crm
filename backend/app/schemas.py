from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InteractionCreate(Body):
    title: str = Field(min_length=1, max_length=250)
    organization_id: str = Field(min_length=1, max_length=64)
    program_id: str | None = None
    product_id: str | None = None
    cycle_label: str = Field(min_length=1, max_length=100)
    owner_id: str = Field(min_length=1, max_length=64)
    contact_id: str | None = None
    contract_id: str | None = None
    license_id: str | None = None
    comment: str | None = Field(default=None, max_length=5000)


class InteractionUpdate(Body):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=250)
    program_id: str | None = None
    product_id: str | None = None
    cycle_label: str | None = Field(default=None, min_length=1, max_length=100)
    contact_id: str | None = None
    contract_id: str | None = None
    license_id: str | None = None

    @field_validator("title", "cycle_label")
    @classmethod
    def forbid_none(cls, v: str | None) -> str | None:
        if v is None:
            raise ValueError("Поле не может быть null.")
        return v


class TransitionCommand(Body):
    transition_code: str = Field(min_length=1, max_length=180)
    expected_revision: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=5000)


class CommentCommand(Body):
    body: str = Field(min_length=1, max_length=5000)
    expected_revision: int = Field(ge=1)


class AssignmentCommand(Body):
    owner_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=5000)


class OrganizationCreate(Body):
    name: str = Field(min_length=1, max_length=250)
    type: Literal["university", "school", "other"] = "university"


class SnapshotRequest(Body):
    as_of: datetime
    knowledge_cutoff: datetime | None = None
    as_of_inclusive: bool = True
    historical_owner_id: str | None = None
    organization_ids: list[str] = Field(default_factory=list, max_length=500)
    program_ids: list[str] = Field(default_factory=list, max_length=500)
    product_ids: list[str] = Field(default_factory=list, max_length=500)
    owner_ids: list[str] = Field(default_factory=list, max_length=500)
    selected_columns: list[str] | None = None

    @field_validator("as_of", "knowledge_cutoff")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Дата должна включать часовой пояс")
        return value


class JobSnapshotRequest(SnapshotRequest):
    as_of: datetime | None = None



class ActivityRequest(Body):
    from_date: datetime = Field(alias="from")
    to_date: datetime = Field(alias="to")
    knowledge_cutoff: datetime | None = None
    historical_owner_id: str | None = None
    organization_ids: list[str] = Field(default_factory=list, max_length=500)
    program_ids: list[str] = Field(default_factory=list, max_length=500)
    product_ids: list[str] = Field(default_factory=list, max_length=500)
    owner_ids: list[str] = Field(default_factory=list, max_length=500)
    selected_columns: list[str] | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    @field_validator("from_date", "to_date", "knowledge_cutoff")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Дата должна включать часовой пояс")
        return value


class CreatedReportRequest(Body):
    from_date: datetime = Field(alias="from")
    to_date: datetime = Field(alias="to")
    knowledge_cutoff: datetime | None = None
    organization_ids: list[str] = Field(default_factory=list, max_length=500)
    owner_ids: list[str] = Field(default_factory=list, max_length=500)
    program_ids: list[str] = Field(default_factory=list, max_length=500)
    product_ids: list[str] = Field(default_factory=list, max_length=500)
    selected_columns: list[str] | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    @field_validator("from_date", "to_date", "knowledge_cutoff")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Дата должна включать часовой пояс")
        return value


class AttachmentRead(BaseModel):
    id: str
    interaction_id: str
    visit_id: str
    file_name: str
    file_size: int
    content_type: str
    checksum: str
    uploaded_by: str
    created_at: str


class ImportCommitRequest(Body):
    import_id: str | None = None
    rows: list[dict] = Field(default_factory=list)


class WorkflowMigrateRequest(Body):
    from_version: int = Field(ge=1, description="Исходная версия workflow")
    to_version: int = Field(ge=1, description="Целевая версия workflow")
    status_mapping: dict[str, str] = Field(min_length=1, description="Матрица сопоставления статусов {старый: новый}")
    expected_card_revisions: dict[str, int] | None = Field(default=None, description="Ожидаемые ревизии карточек для CAS-проверки")


class OrganizationPatch(Body):
    owner_id: str | None = None


class WorkflowVersionCreate(Body):
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    definition: dict = Field(default_factory=dict)


