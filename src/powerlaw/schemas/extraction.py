from uuid import UUID

from pydantic import BaseModel, Field


class ExtractedCondition(BaseModel):
    segment_id: UUID
    trigger: str
    requirement_text: str
    discretionary: bool
    dating_rule: str | None
    waivable_by: str | None
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedDefinedTerm(BaseModel):
    term: str
    definition_text: str
    defining_segment_id: UUID | None
    definition_kind: str


class ExtractedParty(BaseModel):
    canonical_name: str
    entity_type: str | None
    aliases: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
