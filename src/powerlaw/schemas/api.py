from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    aliases: list[str]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ProjectDetail(ProjectRead):
    counters: dict[str, Any]


class ProjectDeleteResult(BaseModel):
    id: UUID
    deleted: bool


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    type: str | None
    title: str | None
    filename: str
    mime: str | None
    execution_date: date | None
    version: int
    content_hash: str
    storage_path: str | None
    status: str | None
    confidence: float | None


class UploadResult(BaseModel):
    document_id: UUID
    job_id: UUID
    filename: str
    status: str


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    document_id: UUID | None
    status: str
    error: str | None
    created_at: datetime
    updated_at: datetime


class SegmentRead(BaseModel):
    id: UUID
    document_id: UUID
    parent_id: UUID | None
    label: str | None
    heading: str | None
    text: str
    char_start: int
    char_end: int
    order_index: int
    children: list["SegmentRead"] = Field(default_factory=list)


class ProvenanceRead(BaseModel):
    segment_id: UUID
    label: str | None
    heading: str | None
    document_id: UUID
    document_title: str | None
    filename: str
    char_start: int
    char_end: int
    text: str


class CrossReferenceRead(BaseModel):
    to_label: str
    to_segment: UUID | None
    resolved: bool
    source: ProvenanceRead | None = None


class ConditionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    segment_id: UUID
    project_id: UUID
    beneficiary_party: UUID | None
    obligor_party: UUID | None
    trigger: str | None
    requirement_text: str
    discretionary: bool
    dating_rule: str | None
    status: str
    waivable_by: str | None
    confidence: float | None
    verification_status: str
    provenance: ProvenanceRead | None = None
    source_context: ProvenanceRead | None = None
    cross_refs: list[CrossReferenceRead] = Field(default_factory=list)
    dependencies: list[UUID] = Field(default_factory=list)
    llm_reason: str | None = None
    llm_call_id: UUID | None = None


class DefinedTermRead(BaseModel):
    id: UUID
    document_id: UUID | None
    term: str
    definition_kind: str | None
    members: list[dict[str, Any]] = Field(default_factory=list)


class PartyRead(BaseModel):
    id: UUID
    project_id: UUID
    canonical_name: str
    entity_type: str | None
    aliases: list[str] = Field(default_factory=list)
    roles: list[dict[str, Any]] = Field(default_factory=list)


class ConditionCorrectRequest(BaseModel):
    field: str
    new_value: Any
    rationale: str
    previous_value: Any | None = None
    author: str = "human"


class ConditionConfirmRequest(BaseModel):
    rationale: str = "Reviewed and confirmed."
    author: str = "human"


ConditionWorkflowStatus = Literal["open", "ongoing", "waived", "verified"]


class ConditionStatusUpdateRequest(BaseModel):
    status: ConditionWorkflowStatus
    rationale: str | None = None
    author: str = "human"


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: UUID
    ts: datetime
    actor_id: str
    actor_type: str
    event_type: str
    target_type: str | None
    target_id: UUID | None
    payload: dict[str, Any]
    derivation: dict[str, Any] | None
    rationale_id: UUID | None
    rationale_text: str | None = None
    rationale_author: str | None = None
    caused_by: int | None
