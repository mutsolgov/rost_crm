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
    organization_ids: list[str] = Field(default_factory=list, max_length=500)
    program_ids: list[str] = Field(default_factory=list, max_length=500)
    product_ids: list[str] = Field(default_factory=list, max_length=500)
    owner_ids: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("as_of", "knowledge_cutoff")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Дата должна включать часовой пояс")
        return value
