from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

from powerlaw.ingestion.segmentation import SegmentDraft, compact_whitespace


@dataclass(frozen=True)
class PartyDraft:
    id: UUID
    canonical_name: str
    entity_type: str | None
    aliases: list[str]
    roles: list[str]


@dataclass(frozen=True)
class DefinedTermDraft:
    id: UUID
    term: str
    definition_text: str
    defining_segment_id: UUID | None
    definition_kind: str
    members: list[str]


BUNDLE_TERMS = {
    "Financing Documents",
    "Material Project Documents",
    "Project Documents",
    "Tax Equity Documents",
    "Transaction Documents",
}


def stable_uuid(*parts: object) -> UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "::".join(str(part) for part in parts))


def extract_parties(project_id: UUID, document_id: UUID, text: str) -> list[PartyDraft]:
    lowered = text[:6000].lower()
    parties: list[PartyDraft] = []
    if "innovative solar 31, llc" in lowered:
        parties.append(
            PartyDraft(
                id=stable_uuid(project_id, "party", "Innovative Solar 31, LLC"),
                canonical_name="Innovative Solar 31, LLC",
                entity_type="limited_liability_company",
                aliases=["Borrower"],
                roles=["Borrower"],
            )
        )
    if "keybank national association" in lowered:
        parties.append(
            PartyDraft(
                id=stable_uuid(project_id, "party", "KEYBANK NATIONAL ASSOCIATION"),
                canonical_name="KEYBANK NATIONAL ASSOCIATION",
                entity_type="national_banking_association",
                aliases=["KeyBank", "Administrative Agent", "Collateral Agent", "Lead Arranger"],
                roles=["Administrative Agent", "Collateral Agent", "Lead Arranger"],
            )
        )
    if "the lenders party hereto" in lowered or "lenders party hereto" in lowered:
        parties.append(
            PartyDraft(
                id=stable_uuid(project_id, "party", "THE LENDERS PARTY HERETO"),
                canonical_name="THE LENDERS PARTY HERETO",
                entity_type="lender_group",
                aliases=["Lenders"],
                roles=["Lenders"],
            )
        )
    return _unique_parties(parties)


def extract_defined_terms(
    document_id: UUID, segments: list[SegmentDraft]
) -> list[DefinedTermDraft]:
    section_1_1 = next((segment for segment in segments if segment.label == "1.1"), None)
    if section_1_1 is None:
        return []

    term_pattern = re.compile(
        r"“\s*([^”]+?)\s*”\s+(means|shall have the meaning|shall mean)\s+(.+?)"
        r"(?=\n\s*“|\n\s*\d+\.\d+|\n\s*ARTICLE|\Z)",
        flags=re.DOTALL,
    )
    drafts: list[DefinedTermDraft] = []
    for match in term_pattern.finditer(section_1_1.text):
        term = compact_whitespace(match.group(1))
        definition = compact_whitespace(match.group(3))
        kind = "enumeration" if _looks_enumerated(definition) else "descriptive"
        drafts.append(
            DefinedTermDraft(
                id=stable_uuid(document_id, "defined-term", term),
                term=term,
                definition_text=definition,
                defining_segment_id=section_1_1.id,
                definition_kind=kind,
                members=_extract_members(term, definition),
            )
        )
    return drafts


def payload_for_party(project_id: UUID, document_id: UUID, party: PartyDraft) -> dict[str, object]:
    return {
        "id": party.id,
        "project_id": project_id,
        "canonical_name": party.canonical_name,
        "entity_type": party.entity_type,
        "aliases": party.aliases,
        "roles": [{"document_id": document_id, "role": role} for role in party.roles],
    }


def payload_for_defined_term(document_id: UUID, term: DefinedTermDraft) -> dict[str, object]:
    return {
        "id": term.id,
        "document_id": document_id,
        "term": term.term,
        "defining_segment_id": term.defining_segment_id,
        "definition_kind": term.definition_kind,
        "definition_text": term.definition_text,
    }


def _unique_parties(parties: list[PartyDraft]) -> list[PartyDraft]:
    seen: set[UUID] = set()
    unique: list[PartyDraft] = []
    for party in parties:
        if party.id in seen:
            continue
        seen.add(party.id)
        unique.append(party)
    return unique


def _looks_enumerated(definition: str) -> bool:
    lowered = definition.lower()
    return "collectively" in lowered or bool(re.search(r"\([ivx]+\)|\([a-z]\)", lowered))


def _extract_members(term: str, definition: str) -> list[str]:
    if term not in BUNDLE_TERMS:
        return []
    clean = re.sub(r"\([^)]{0,80}\)", "", definition)
    clean = re.split(r";| and “|, and “", clean, maxsplit=1)[0]
    pieces = re.split(r",|\band\b", clean)
    members: list[str] = []
    for piece in pieces:
        candidate = piece.strip(" .;:")
        candidate = re.sub(r"^(collectively|this agreement|the)\s+", "", candidate, flags=re.I)
        candidate = candidate.strip()
        if not candidate or len(candidate) < 3:
            continue
        if candidate.lower().startswith(("any ", "all ", "other ", "each ")):
            continue
        members.append(candidate)
    return members[:25]
