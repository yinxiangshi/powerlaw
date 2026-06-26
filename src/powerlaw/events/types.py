from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ActorType(StrEnum):
    SYSTEM = "system"
    MODEL = "model"
    HUMAN = "human"


class EventType(StrEnum):
    PROJECT_CREATED = "ProjectCreated"
    PROJECT_DELETED = "ProjectDeleted"
    DOCUMENT_INGESTED = "DocumentIngested"
    DOCUMENT_TYPED = "DocumentTyped"
    DOCUMENT_SEGMENTED = "DocumentSegmented"
    CONDITION_EXTRACTED = "ConditionExtracted"
    DEFINED_TERM_EXTRACTED = "DefinedTermExtracted"
    PARTY_IDENTIFIED = "PartyIdentified"
    TERM_MEMBERSHIP_RESOLVED = "TermMembershipResolved"
    CROSS_REFERENCE_RESOLVED = "CrossReferenceResolved"
    DEPENDENCY_LINKED = "DependencyLinked"
    EVIDENCE_ARTIFACT_EXPECTED = "EvidenceArtifactExpected"
    EXTRACTION_FLAGGED = "ExtractionFlagged"
    DOCUMENT_LINKED = "DocumentLinked"
    DOCUMENT_ERRORED = "DocumentErrored"
    CONDITION_CONFIRMED = "ConditionConfirmed"
    CONDITION_CORRECTED = "ConditionCorrected"
    DOCUMENT_TAGGED = "DocumentTagged"
    DOCUMENT_CONTEXT_CORRECTED = "DocumentContextCorrected"
    DOCUMENT_EDITED = "DocumentEdited"
    GENERATED_CONTENT_INSERTED = "GeneratedContentInserted"
    GENERATED_CONTENT_EDITED = "GeneratedContentEdited"
    DRAFTING_PREFERENCE_LEARNED = "DraftingPreferenceLearned"
    JOB_CREATED = "JobCreated"
    JOB_UPDATED = "JobUpdated"


class Derivation(BaseModel):
    model: str | None = None
    prompt_version: str | None = None
    input_spans: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ProjectCreatedPayload(BaseModel):
    id: UUID
    name: str
    aliases: list[str] = Field(default_factory=list)


class ProjectDeletedPayload(BaseModel):
    id: UUID


class DocumentIngestedPayload(BaseModel):
    id: UUID
    filename: str
    mime: str | None = None
    content_hash: str
    storage_path: str
    version: int = 1


class SegmentPayload(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    label: str | None = None
    heading: str | None = None
    text: str
    char_start: int
    char_end: int
    order_index: int


class DocumentSegmentedPayload(BaseModel):
    document_id: UUID
    segments: list[SegmentPayload]


class ConditionPayload(BaseModel):
    id: UUID
    segment_id: UUID
    beneficiary_party: UUID | None = None
    obligor_party: UUID | None = None
    trigger: str
    requirement_text: str
    discretionary: bool = False
    dating_rule: str | None = None
    status: str = "open"
    waivable_by: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    verification_status: str = "unverified"


class CorrectConditionPayload(BaseModel):
    field: str
    before: Any = None
    after: Any
