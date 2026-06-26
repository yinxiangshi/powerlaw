from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from powerlaw.ingestion.entities import DefinedTermDraft
from powerlaw.ingestion.extraction import ConditionDraft
from powerlaw.ingestion.segmentation import SegmentDraft


@dataclass(frozen=True)
class CrossRefDraft:
    from_segment: UUID
    to_label: str
    to_segment: UUID | None
    resolved: bool


@dataclass(frozen=True)
class DependencyDraft:
    from_condition: UUID
    to_condition: UUID
    source_segment: UUID


def resolve_condition_cross_refs(
    *,
    conditions: list[ConditionDraft],
    segments: list[SegmentDraft],
) -> tuple[list[CrossRefDraft], list[DependencyDraft], list[str]]:
    segment_by_label = {segment.label: segment for segment in segments if segment.label}
    condition_by_label = {condition.label: condition for condition in conditions}
    cross_refs: list[CrossRefDraft] = []
    dependencies: list[DependencyDraft] = []
    unresolved: list[str] = []

    for condition in conditions:
        labels = _section_refs(condition.requirement_text)
        for label in labels:
            segment = segment_by_label.get(label)
            cross_refs.append(
                CrossRefDraft(
                    from_segment=condition.segment_id,
                    to_label=label,
                    to_segment=segment.id if segment else None,
                    resolved=segment is not None,
                )
            )
            if segment is None:
                unresolved.append(f"{condition.label} references unresolved Section {label}")
                continue
            target_condition = condition_by_label.get(label)
            if target_condition is not None and target_condition.id != condition.id:
                dependencies.append(
                    DependencyDraft(
                        from_condition=condition.id,
                        to_condition=target_condition.id,
                        source_segment=condition.segment_id,
                    )
                )
    return cross_refs, dependencies, unresolved


def resolve_term_memberships(
    terms: Sequence[DefinedTermDraft | Any], documents: Sequence[Any]
) -> list[dict[str, object]]:
    documents_by_name = _document_name_index(documents)
    memberships: list[dict[str, object]] = []
    for term in terms:
        for member in term.members:
            member_document = _match_document(member, documents_by_name)
            memberships.append(
                {
                    "defined_term": term.id,
                    "member_name": member,
                    "member_document": member_document,
                    "member_party": None,
                    "resolved": member_document is not None,
                }
            )
    return memberships


def unresolved_memberships(memberships: list[dict[str, object]]) -> list[str]:
    return [
        f"{membership['member_name']} referenced by bundle but missing from data room"
        for membership in memberships
        if not membership.get("resolved")
    ]


def _section_refs(text: str) -> list[str]:
    refs = re.findall(r"Section\s+(\d+\.\d+(?:\([a-z]{1,2}\))?)", text)
    return sorted(set(refs))


def _document_name_index(documents: Sequence[Any]) -> dict[str, UUID]:
    index: dict[str, UUID] = {}
    for document in documents:
        candidates = [document.title or "", document.filename, document.type or ""]
        for candidate in candidates:
            normalized = _normalize_name(candidate)
            if normalized:
                index[normalized] = document.id
        if document.type == "mipa":
            index["mipa"] = document.id
            index["membership interest purchase agreement"] = document.id
        elif document.type == "epc":
            index["epc agreement"] = document.id
        elif document.type == "tax_equity_ecca":
            index["tax equity ecca"] = document.id
        elif document.type == "depositary":
            index["depositary agreement"] = document.id
        elif document.type == "accounts":
            index["accounts agreement"] = document.id
    return index


def _match_document(member: str, index: dict[str, UUID]) -> UUID | None:
    normalized = _normalize_name(member)
    if normalized in index:
        return index[normalized]
    for key, document_id in index.items():
        if normalized and (normalized in key or key in normalized):
            return document_id
    return None


def _normalize_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()
