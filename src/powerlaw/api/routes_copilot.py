from __future__ import annotations

from difflib import SequenceMatcher, unified_diff
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.config import Settings, get_settings
from powerlaw.db import get_session
from powerlaw.events.store import append_event
from powerlaw.events.types import ActorType, EventType
from powerlaw.llm.client import LlmClient, LlmDisabledError
from powerlaw.models.tables import (
    Condition,
    Document,
    Event,
    Party,
    PartyAlias,
    Project,
    Rationale,
    Segment,
)
from powerlaw.repositories.read import defined_term_reads, party_reads

router = APIRouter(prefix="/copilot", tags=["copilot"])
COPILOT_PROMPT_VERSION = "word-copilot-drafting-v1"


class DocumentProbe(BaseModel):
    filename: str | None = None
    text: str = ""
    custom_properties: dict[str, Any] = Field(default_factory=dict)
    max_candidates: int = Field(default=5, ge=1, le=20)


class ProjectCandidate(BaseModel):
    project_id: UUID
    project_name: str
    document_id: UUID | None = None
    document_title: str | None = None
    filename: str | None = None
    confidence: float
    reasons: list[str] = Field(default_factory=list)
    requires_confirmation: bool


class IdentifyDocumentResponse(BaseModel):
    candidates: list[ProjectCandidate]
    needs_confirmation: bool


class ConfirmDocumentContextRequest(BaseModel):
    project_id: UUID
    document_id: UUID | None = None
    contract_type: str | None = None
    corrected: bool = False
    rationale: str | None = None
    author: str = "word-addin"


class ConfirmDocumentContextResponse(BaseModel):
    project_id: UUID
    document_id: UUID | None
    contract_type: str | None
    tags: dict[str, str]
    event_id: int


class GenerateRequest(BaseModel):
    project_id: UUID
    document_id: UUID | None = None
    instruction: str
    selected_text: str | None = None
    content_kind: str = "clause"
    author: str = "word-addin"


class GenerateResponse(BaseModel):
    generated_content_id: UUID
    generation_event_id: int
    text: str
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    needs_rationale_on_edit: bool = True


class EditObservationRequest(BaseModel):
    project_id: UUID
    document_id: UUID | None = None
    generated_content_id: UUID
    insertion_id: UUID | None = None
    before_text: str
    after_text: str
    rationale: str
    categories: list[str] = Field(default_factory=list)
    author: str = "word-addin"
    diff: str | None = None


class EditObservationResponse(BaseModel):
    event_id: int
    rationale_id: UUID
    diff: str
    accepted_for_memory: bool


class DocumentEditObservationRequest(BaseModel):
    project_id: UUID
    document_id: UUID | None = None
    before_text: str
    after_text: str
    rationale: str
    categories: list[str] = Field(default_factory=list)
    author: str = "word-addin"
    diff: str | None = None


class CopilotContextResponse(BaseModel):
    project_id: UUID
    document_id: UUID | None
    parties: list[dict[str, Any]] = Field(default_factory=list)
    defined_terms: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    recent_rationales: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/identify-document", response_model=IdentifyDocumentResponse)
async def identify_document(
    body: DocumentProbe, session: AsyncSession = Depends(get_session)
) -> IdentifyDocumentResponse:
    project_rows = list((await session.scalars(select(Project).order_by(Project.name))).all())
    documents = (await session.scalars(select(Document))).all()

    aliases_by_project = await _party_aliases_by_project(session)
    documents_by_project: dict[UUID, list[Document]] = {}
    for document in documents:
        documents_by_project.setdefault(document.project_id, []).append(document)

    haystack = _normalize(f"{body.filename or ''}\n{body.text[:20000]}")
    custom_project_id = _uuid_from_property(body.custom_properties, "powerlaw_project_id")
    custom_document_id = _uuid_from_property(body.custom_properties, "powerlaw_document_id")
    candidates: list[ProjectCandidate] = []

    for project in project_rows:
        score, reasons = _score_project(
            project_id=project.id,
            project_name=project.name,
            aliases=list(project.aliases or []) + aliases_by_project.get(project.id, []),
            haystack=haystack,
            custom_project_id=custom_project_id,
        )
        best_document, document_score, document_reasons = _best_document_match(
            documents_by_project.get(project.id, []),
            filename=body.filename or "",
            haystack=haystack,
            custom_document_id=custom_document_id,
        )
        combined = min(score + document_score, 0.99)
        reasons.extend(document_reasons)
        if combined <= 0:
            continue
        candidates.append(
            ProjectCandidate(
                project_id=project.id,
                project_name=project.name,
                document_id=best_document.id if best_document else None,
                document_title=best_document.title if best_document else None,
                filename=best_document.filename if best_document else None,
                confidence=round(combined, 2),
                reasons=reasons,
                requires_confirmation=combined < 0.82,
            )
        )

    candidates.sort(key=lambda item: item.confidence, reverse=True)
    candidates = candidates[: body.max_candidates]
    return IdentifyDocumentResponse(
        candidates=candidates,
        needs_confirmation=not candidates or candidates[0].requires_confirmation,
    )


@router.post("/confirm-document-context", response_model=ConfirmDocumentContextResponse)
async def confirm_document_context(
    body: ConfirmDocumentContextRequest, session: AsyncSession = Depends(get_session)
) -> ConfirmDocumentContextResponse:
    project = await session.get(Project, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if body.document_id is not None:
        document = await session.get(Document, body.document_id)
        if document is None or document.project_id != body.project_id:
            raise HTTPException(status_code=404, detail="document not found for project")

    rationale_text = body.rationale or (
        "Corrected the Word document project context."
        if body.corrected
        else "Confirmed the Word document project context."
    )
    rationale = Rationale(
        text=rationale_text,
        author=body.author,
        structured_tags={
            "source": "word_addin",
            "corrected": body.corrected,
            "contract_type": body.contract_type,
        },
        is_privileged=True,
    )
    session.add(rationale)
    await session.flush()
    event = await append_event(
        session,
        project_id=body.project_id,
        actor_id=body.author,
        actor_type=ActorType.HUMAN,
        event_type=(
            EventType.DOCUMENT_CONTEXT_CORRECTED if body.corrected else EventType.DOCUMENT_TAGGED
        ),
        target_type="document" if body.document_id else "project",
        target_id=body.document_id or body.project_id,
        payload={
            "project_id": body.project_id,
            "document_id": body.document_id,
            "contract_type": body.contract_type,
            "source": "word_addin",
            "corrected": body.corrected,
        },
        rationale_id=rationale.id,
    )
    await session.commit()
    tags = {
        "powerlaw_project_id": str(body.project_id),
        "powerlaw_project_name": project.name,
    }
    if body.document_id is not None:
        tags["powerlaw_document_id"] = str(body.document_id)
    if body.contract_type:
        tags["powerlaw_contract_type"] = body.contract_type
    return ConfirmDocumentContextResponse(
        project_id=body.project_id,
        document_id=body.document_id,
        contract_type=body.contract_type,
        tags=tags,
        event_id=event.id,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_content(
    body: GenerateRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> GenerateResponse:
    project = await session.get(Project, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if body.document_id is not None:
        document = await session.get(Document, body.document_id)
        if document is None or document.project_id != body.project_id:
            raise HTTPException(status_code=404, detail="document not found for project")

    snippets = await _context_snippets(session, body.project_id, body.document_id)
    rationales = await _recent_rationales(session, body.project_id, 6)
    parties = await party_reads(session, body.project_id)
    document_ids = [
        document.id
        for document in (
            await session.scalars(select(Document).where(Document.project_id == body.project_id))
        ).all()
    ]
    defined_terms = await defined_term_reads(session, document_ids)
    prompt = _draft_prompt(
        project_name=project.name,
        body=body,
        snippets=snippets,
        rationales=rationales,
        parties=[party.model_dump(mode="json") for party in parties[:12]],
        defined_terms=[term.model_dump(mode="json") for term in defined_terms[:18]],
    )
    model_name = "deterministic-mvp"
    confidence = 0.55
    llm_call_id: str | None = None
    if settings.openai_api_key:
        try:
            generated_text, response_payload = await LlmClient(settings).call_text(
                session,
                document_id=body.document_id,
                segment_id=None,
                purpose="word_copilot_generate",
                prompt_version=COPILOT_PROMPT_VERSION,
                prompt=prompt,
            )
        except LlmDisabledError:
            generated_text = _draft_placeholder(project.name, body, snippets)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}") from exc
        else:
            generated_text = _clean_generated_text(generated_text)
            model_name = settings.openai_model
            confidence = 0.76
            llm_call_id = response_payload.get("_llm_call_id")
    else:
        generated_text = _draft_placeholder(project.name, body, snippets)

    generated_content_id = uuid4()
    event = await append_event(
        session,
        project_id=body.project_id,
        actor_id="powerlaw-copilot",
        actor_type=ActorType.MODEL,
        event_type=EventType.GENERATED_CONTENT_INSERTED,
        target_type="generated_content",
        target_id=generated_content_id,
        payload={
            "id": generated_content_id,
            "project_id": body.project_id,
            "document_id": body.document_id,
            "content_kind": body.content_kind,
            "instruction": body.instruction,
            "selected_text": body.selected_text,
            "text": generated_text,
            "source": "word_addin",
            "requires_rationale_on_edit": True,
        },
        derivation={
            "model": model_name,
            "prompt_version": COPILOT_PROMPT_VERSION,
            "llm_call_id": llm_call_id,
            "input_spans": snippets,
            "confidence": confidence,
        },
    )
    await session.commit()
    return GenerateResponse(
        generated_content_id=generated_content_id,
        generation_event_id=event.id,
        text=generated_text,
        provenance=snippets,
    )


@router.post("/edit-observations", response_model=EditObservationResponse)
async def observe_edit(
    body: EditObservationRequest, session: AsyncSession = Depends(get_session)
) -> EditObservationResponse:
    if not body.rationale.strip():
        raise HTTPException(status_code=422, detail="rationale is required")

    project = await session.get(Project, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if body.document_id is not None:
        document = await session.get(Document, body.document_id)
        if document is None or document.project_id != body.project_id:
            raise HTTPException(status_code=404, detail="document not found for project")

    diff = body.diff or _unified_diff(body.before_text, body.after_text)
    operation = _edit_operation(body.before_text, body.after_text)
    rationale = Rationale(
        text=body.rationale.strip(),
        author=body.author,
        structured_tags={
            "source": "word_addin",
            "categories": body.categories,
            "generated_content_id": str(body.generated_content_id),
            "insertion_id": str(body.insertion_id) if body.insertion_id else None,
            "operation": operation,
        },
        is_privileged=True,
    )
    session.add(rationale)
    await session.flush()
    event = await append_event(
        session,
        project_id=body.project_id,
        actor_id=body.author,
        actor_type=ActorType.HUMAN,
        event_type=EventType.GENERATED_CONTENT_EDITED,
        target_type="generated_content",
        target_id=body.generated_content_id,
        payload={
            "generated_content_id": body.generated_content_id,
            "insertion_id": body.insertion_id,
            "document_id": body.document_id,
            "before_text": body.before_text,
            "after_text": body.after_text,
            "diff": diff,
            "categories": body.categories,
            "operation": operation,
            "source": "word_addin",
        },
        rationale_id=rationale.id,
    )
    await session.commit()
    return EditObservationResponse(
        event_id=event.id,
        rationale_id=rationale.id,
        diff=diff,
        accepted_for_memory=True,
    )


@router.post("/document-edit-observations", response_model=EditObservationResponse)
async def observe_document_edit(
    body: DocumentEditObservationRequest, session: AsyncSession = Depends(get_session)
) -> EditObservationResponse:
    if not body.rationale.strip():
        raise HTTPException(status_code=422, detail="rationale is required")

    project = await session.get(Project, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if body.document_id is not None:
        document = await session.get(Document, body.document_id)
        if document is None or document.project_id != body.project_id:
            raise HTTPException(status_code=404, detail="document not found for project")

    diff = body.diff or _unified_diff(body.before_text, body.after_text)
    operation = _edit_operation(body.before_text, body.after_text)
    rationale = Rationale(
        text=body.rationale.strip(),
        author=body.author,
        structured_tags={
            "source": "word_addin",
            "categories": body.categories,
            "edit_scope": "document",
            "operation": operation,
        },
        is_privileged=True,
    )
    session.add(rationale)
    await session.flush()
    event = await append_event(
        session,
        project_id=body.project_id,
        actor_id=body.author,
        actor_type=ActorType.HUMAN,
        event_type=EventType.DOCUMENT_EDITED,
        target_type="document" if body.document_id else "project_document",
        target_id=body.document_id or body.project_id,
        payload={
            "document_id": body.document_id,
            "before_text": body.before_text,
            "after_text": body.after_text,
            "diff": diff,
            "categories": body.categories,
            "operation": operation,
            "source": "word_addin",
        },
        rationale_id=rationale.id,
    )
    await session.commit()
    return EditObservationResponse(
        event_id=event.id,
        rationale_id=rationale.id,
        diff=diff,
        accepted_for_memory=True,
    )


@router.get("/context", response_model=CopilotContextResponse)
async def copilot_context(
    project_id: UUID,
    document_id: UUID | None = None,
    limit: int = Query(default=8, ge=1, le=25),
    session: AsyncSession = Depends(get_session),
) -> CopilotContextResponse:
    documents = (
        await session.scalars(select(Document).where(Document.project_id == project_id))
    ).all()
    document_ids = [document.id for document in documents]
    terms = await defined_term_reads(session, document_ids)
    parties = await party_reads(session, project_id)
    condition_rows = (
        await session.scalars(
            select(Condition)
            .where(Condition.project_id == project_id)
            .order_by(Condition.updated_at.desc())
            .limit(limit)
        )
    ).all()
    rationales = await _recent_rationales(session, project_id, limit)
    return CopilotContextResponse(
        project_id=project_id,
        document_id=document_id,
        parties=[party.model_dump(mode="json") for party in parties[:limit]],
        defined_terms=[term.model_dump(mode="json") for term in terms[:limit]],
        conditions=[
            {
                "id": str(condition.id),
                "trigger": condition.trigger,
                "requirement_text": condition.requirement_text,
                "status": condition.status,
                "verification_status": condition.verification_status,
            }
            for condition in condition_rows
        ],
        recent_rationales=rationales,
    )


async def _party_aliases_by_project(session: AsyncSession) -> dict[UUID, list[str]]:
    rows = (
        await session.execute(
            select(Party.project_id, Party.canonical_name, PartyAlias.alias)
            .outerjoin(PartyAlias, PartyAlias.party_id == Party.id)
            .order_by(Party.canonical_name)
        )
    ).all()
    aliases: dict[UUID, list[str]] = {}
    for project_id, canonical_name, alias in rows:
        values = aliases.setdefault(project_id, [])
        values.append(canonical_name)
        if alias:
            values.append(alias)
    return aliases


def _score_project(
    *,
    project_id: UUID,
    project_name: str,
    aliases: list[str],
    haystack: str,
    custom_project_id: UUID | None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if custom_project_id == project_id:
        score += 0.75
        reasons.append("document carries a saved PowerLaw project tag")
    for label, weight in [(project_name, 0.35), *[(alias, 0.18) for alias in aliases]]:
        needle = _normalize(label)
        if len(needle) >= 4 and needle in haystack:
            score += weight
            reasons.append(f"matched project signal: {label}")
            if score >= 0.55:
                break
    return min(score, 0.85), reasons


def _best_document_match(
    documents: list[Document],
    *,
    filename: str,
    haystack: str,
    custom_document_id: UUID | None,
) -> tuple[Document | None, float, list[str]]:
    best: tuple[Document | None, float, list[str]] = (None, 0.0, [])
    incoming_filename = _normalize(filename)
    for document in documents:
        score = 0.0
        reasons: list[str] = []
        if custom_document_id == document.id:
            score += 0.45
            reasons.append("document carries a saved PowerLaw document tag")
        stored_filename = _normalize(document.filename)
        if incoming_filename and stored_filename:
            similarity = SequenceMatcher(a=incoming_filename, b=stored_filename).ratio()
            if similarity > 0.72:
                score += 0.28
                reasons.append("filename resembles an ingested document")
        if document.title and _normalize(document.title) in haystack:
            score += 0.22
            reasons.append("document title appears in the Word text")
        if score > best[1]:
            best = (document, min(score, 0.5), reasons)
    return best


async def _context_snippets(
    session: AsyncSession, project_id: UUID, document_id: UUID | None
) -> list[dict[str, Any]]:
    query = select(Segment, Document).join(Document, Document.id == Segment.document_id)
    query = query.where(Document.project_id == project_id)
    if document_id is not None:
        query = query.where(Segment.document_id == document_id)
    rows = (await session.execute(query.order_by(Segment.order_index).limit(3))).all()
    return [
        {
            "document_id": str(document.id),
            "segment_id": str(segment.id),
            "filename": document.filename,
            "label": segment.label,
            "heading": segment.heading,
            "text": segment.text[:1200],
        }
        for segment, document in rows
    ]


async def _recent_rationales(
    session: AsyncSession, project_id: UUID, limit: int
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Event, Rationale)
            .join(Rationale, Rationale.id == Event.rationale_id)
            .where(Event.project_id == project_id)
            .order_by(Event.id.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "event_id": event.id,
            "event_type": event.event_type,
            "rationale": rationale.text,
            "tags": rationale.structured_tags,
            "created_at": rationale.created_at.isoformat(),
        }
        for event, rationale in rows
    ]


def _draft_prompt(
    *,
    project_name: str,
    body: GenerateRequest,
    snippets: list[dict[str, Any]],
    rationales: list[dict[str, Any]],
    parties: list[dict[str, Any]],
    defined_terms: list[dict[str, Any]],
) -> str:
    selected = (body.selected_text or "").strip()
    snippet_block = _numbered_block(
        [
            _compact(
                f"{item.get('filename')} {item.get('label') or ''} "
                f"{item.get('heading') or ''}\n{item.get('text') or ''}"
            )
            for item in snippets
        ],
        empty="No source snippets available.",
    )
    rationale_block = _numbered_block(
        [
            _compact(f"{item.get('event_type')}: {item.get('rationale')}")
            for item in rationales
        ],
        empty="No prior drafting rationales available.",
    )
    party_block = _numbered_block(
        [
            _compact(
                f"{item.get('canonical_name')} "
                f"aliases={item.get('aliases') or []} roles={item.get('roles') or []}"
            )
            for item in parties
        ],
        empty="No parties available.",
    )
    term_block = _numbered_block(
        [
            _compact(
                f"{item.get('term')} kind={item.get('definition_kind')} "
                f"members={item.get('members') or []}"
            )
            for item in defined_terms
        ],
        empty="No defined terms available.",
    )
    return f"""
You are PowerLaw, a drafting copilot for project-finance lawyers working in Microsoft Word.

Draft one {body.content_kind} for the active matter.

Matter:
{project_name}

Lawyer instruction:
{body.instruction.strip()}

Selected Word text, if any:
{selected or "No active selection provided."}

Known parties:
{party_block}

Known defined terms:
{term_block}

Relevant source context:
{snippet_block}

Prior lawyer edit rationales to honor as drafting memory:
{rationale_block}

Rules:
- Return only the draft legal text that should be inserted into Word.
- Do not include markdown fences, explanations, citations, or headings unless requested.
- Use defined terms consistently when the context supports them.
- Preserve bracketed placeholders for missing business facts instead of inventing facts.
- Keep the language practical, negotiated, and suitable for a lawyer to edit.
- If instruction conflicts with source context, draft the safest narrow version with placeholders.
""".strip()


def _draft_placeholder(
    project_name: str, body: GenerateRequest, snippets: list[dict[str, Any]]
) -> str:
    selected = (body.selected_text or "").strip()
    basis = selected or (snippets[0]["text"].strip() if snippets else "")
    basis_note = f"\n\nReference context:\n{basis[:900]}" if basis else ""
    return (
        f"{body.content_kind.title()} draft for {project_name}\n\n"
        f"Instruction: {body.instruction.strip()}\n\n"
        "Draft language:\n"
        "[Replace this MVP placeholder with model-generated language once the LLM "
        "generation path is enabled. Keep the content control wrapper so edits can "
        "be reviewed with a rationale.]"
        f"{basis_note}"
    )


def _clean_generated_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    lowered = cleaned.lower()
    for prefix in ("draft language:", "draft:", "clause:", "section:"):
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
            break
    return cleaned


def _numbered_block(items: list[str], *, empty: str) -> str:
    values = [item for item in items if item]
    if not values:
        return empty
    return "\n".join(f"{index}. {value[:1800]}" for index, value in enumerate(values, 1))


def _compact(value: str) -> str:
    return " ".join(value.split())


def _unified_diff(before: str, after: str) -> str:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    return "\n".join(
        unified_diff(
            before_lines,
            after_lines,
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )


def _edit_operation(before: str, after: str) -> str:
    if before.strip() and not after.strip():
        return "deleted"
    if after.strip() and not before.strip():
        return "inserted"
    return "edited"


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _uuid_from_property(properties: dict[str, Any], key: str) -> UUID | None:
    raw = properties.get(key) or properties.get(key.replace("_", "-"))
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None
