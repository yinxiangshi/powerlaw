import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

try:
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover - import exists after uv sync
    Vector = None  # type: ignore[assignment]

JSONType = JSONB().with_variant(JSON, "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow
    )


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_event: Mapped[int | None] = mapped_column(BigInteger)


class Rationale(Base):
    __tablename__ = "rationales"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_tags: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    author: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    is_privileged: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "actor_type in ('system', 'model', 'human')", name="ck_event_actor_type"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    derivation: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    rationale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rationales.id")
    )
    caused_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("events.id"))


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    type: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str | None] = mapped_column(Text)
    execution_date: Mapped[Any | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text, default="ingested")
    confidence: Mapped[float | None] = mapped_column(Float)
    updated_by_event: Mapped[int | None] = mapped_column(BigInteger)


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (
        Index("ix_segments_document_order", "document_id", "order_index"),
        Index("ix_segments_document_label", "document_id", "label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("segments.id")
    )
    label: Mapped[str | None] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class Condition(Base, TimestampMixin):
    __tablename__ = "conditions"
    __table_args__ = (
        CheckConstraint(
            "verification_status in ('unverified', 'lawyer_confirmed', 'lawyer_corrected')",
            name="ck_condition_verification_status",
        ),
        Index("ix_conditions_project_trigger", "project_id", "trigger"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    segment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("segments.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    beneficiary_party: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parties.id")
    )
    obligor_party: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parties.id")
    )
    trigger: Mapped[str | None] = mapped_column(Text)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    discretionary: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    dating_rule: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    waivable_by: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    verification_status: Mapped[str] = mapped_column(
        Text, default="unverified", server_default="unverified"
    )
    updated_by_event: Mapped[int | None] = mapped_column(BigInteger)


class DefinedTerm(Base):
    __tablename__ = "defined_terms"
    __table_args__ = (
        UniqueConstraint("document_id", "term", name="uq_defined_terms_document_term"),
        Index("ix_defined_terms_document_term", "document_id", "term"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id")
    )
    term: Mapped[str] = mapped_column(Text, nullable=False)
    defining_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("segments.id")
    )
    definition_kind: Mapped[str | None] = mapped_column(Text)


class Party(Base):
    __tablename__ = "parties"
    __table_args__ = (
        UniqueConstraint("project_id", "canonical_name", name="uq_party_project_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)


class PartyAlias(Base):
    __tablename__ = "party_aliases"
    __table_args__ = (UniqueConstraint("party_id", "alias", name="uq_party_alias"),)

    party_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parties.id"), primary_key=True
    )
    alias: Mapped[str] = mapped_column(Text, primary_key=True)


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    expected_by_condition: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conditions.id")
    )
    fulfilled_by_document: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id")
    )
    provider_party: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parties.id")
    )
    description: Mapped[str | None] = mapped_column(Text)


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id")
    )
    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("segments.id")
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )


class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("from_condition", "to_condition", name="uq_dependency"),
    )

    from_condition: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conditions.id"), primary_key=True
    )
    to_condition: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conditions.id"), primary_key=True
    )
    source_segment: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("segments.id")
    )


class TermMembership(Base):
    __tablename__ = "term_membership"
    __table_args__ = (
        UniqueConstraint("defined_term", "member_name", name="uq_term_membership_name"),
    )

    defined_term: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("defined_terms.id"), primary_key=True
    )
    member_name: Mapped[str] = mapped_column(Text, primary_key=True)
    member_document: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id")
    )
    member_party: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parties.id")
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class CrossRef(Base):
    __tablename__ = "cross_refs"
    __table_args__ = (
        UniqueConstraint("from_segment", "to_label", name="uq_cross_ref_label"),
    )

    from_segment: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("segments.id"), primary_key=True
    )
    to_label: Mapped[str] = mapped_column(Text, primary_key=True)
    to_segment: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("segments.id")
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class PartyRole(Base):
    __tablename__ = "party_roles"
    __table_args__ = (
        UniqueConstraint("party_id", "document_id", "role", name="uq_party_role"),
    )

    party_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parties.id"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, primary_key=True)


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id"), primary_key=True
    )
    if Vector is not None:
        embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    else:
        embedding: Mapped[list[float] | None] = mapped_column(JSONType)


class IngestionJob(Base, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id")
    )
    status: Mapped[str] = mapped_column(Text, default="queued", server_default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    updated_by_event: Mapped[int | None] = mapped_column(BigInteger)
