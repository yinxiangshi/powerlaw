from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from uuid import UUID


@dataclass(frozen=True)
class SegmentDraft:
    id: UUID
    document_id: UUID
    parent_id: UUID | None
    label: str
    heading: str | None
    text: str
    char_start: int
    char_end: int
    order_index: int

    def event_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("document_id")
        return payload


ARTICLE_RE = re.compile(r"(?m)^\s*ARTICLE\s+(\d+)\s+([A-Z0-9][A-Z0-9 ,;:'&()/.-]+?)\s*$")
SECTION_RE = re.compile(r"(?m)^\s*(\d+\.\d+)\s+([^\n]{3,1200})$")
ALPHA_CLAUSE_RE = re.compile(r"(?m)^\s*\(([a-z]{1,2})\)\s+")
ROMAN_CLAUSE_RE = re.compile(r"(?m)^\s*\((i{1,3}|iv|v|vi{0,3}|ix|x)\)\s+")


def segment_document(text: str, document_id: UUID) -> list[SegmentDraft]:
    body_start = find_contract_body_start(text)
    body = text[body_start:]
    article_matches = list(ARTICLE_RE.finditer(body))
    if not article_matches:
        return [
            SegmentDraft(
                id=uuid.uuid4(),
                document_id=document_id,
                parent_id=None,
                label="document",
                heading=None,
                text=text,
                char_start=0,
                char_end=len(text),
                order_index=0,
            )
        ]

    drafts: list[SegmentDraft] = []
    article_bounds: list[tuple[re.Match[str], int, int, UUID]] = []
    for index, match in enumerate(article_matches):
        start = body_start + match.start()
        end = (
            body_start + article_matches[index + 1].start()
            if index + 1 < len(article_matches)
            else len(text)
        )
        article_id = uuid.uuid4()
        label = f"ARTICLE {match.group(1)}"
        heading = compact_whitespace(match.group(2).title())
        article_bounds.append((match, start, end, article_id))
        drafts.append(
            SegmentDraft(
                id=article_id,
                document_id=document_id,
                parent_id=None,
                label=label,
                heading=heading,
                text=text[start:end],
                char_start=start,
                char_end=end,
                order_index=len(drafts),
            )
        )

    section_matches = [
        match
        for match in SECTION_RE.finditer(body)
        if _looks_like_real_section_heading(match.group(2))
    ]
    section_bounds: list[tuple[re.Match[str], int, int, UUID]] = []
    for index, match in enumerate(section_matches):
        start = body_start + match.start()
        next_section_start = (
            body_start + section_matches[index + 1].start()
            if index + 1 < len(section_matches)
            else len(text)
        )
        article_parent = _containing_article(article_bounds, start)
        article_end = article_parent[2] if article_parent else len(text)
        end = min(next_section_start, article_end)
        section_id = uuid.uuid4()
        section_bounds.append((match, start, end, section_id))
        drafts.append(
            SegmentDraft(
                id=section_id,
                document_id=document_id,
                parent_id=article_parent[3] if article_parent else None,
                label=match.group(1),
                heading=_section_heading(match.group(2)),
                text=text[start:end],
                char_start=start,
                char_end=end,
                order_index=len(drafts),
            )
        )

    for section_match, section_start, section_end, section_id in section_bounds:
        section_label = section_match.group(1)
        section_text = text[section_start:section_end]
        clause_matches = _top_level_alpha_matches(section_text)
        for clause_index, clause_match in enumerate(clause_matches):
            start = section_start + clause_match.start()
            end = (
                section_start + clause_matches[clause_index + 1].start()
                if clause_index + 1 < len(clause_matches)
                else section_end
            )
            clause_label = f"{section_label}({clause_match.group(1)})"
            clause_text = text[start:end]
            clause_id = uuid.uuid4()
            drafts.append(
                SegmentDraft(
                    id=clause_id,
                    document_id=document_id,
                    parent_id=section_id,
                    label=clause_label,
                    heading=_clause_heading(clause_text),
                    text=clause_text,
                    char_start=start,
                    char_end=end,
                    order_index=len(drafts),
                )
            )
            drafts.extend(
                _roman_subsegments(
                    document_id=document_id,
                    parent_id=clause_id,
                    parent_label=clause_label,
                    parent_text=text,
                    start=start,
                    end=end,
                    first_order=len(drafts),
                )
            )

    return sorted(drafts, key=lambda draft: (draft.char_start, draft.order_index))


def find_contract_body_start(text: str) -> int:
    candidates = [
        r"\n\s*AGREEMENT\s*\n\s*NOW THEREFORE",
        r"\n\s*THIS\s+[A-Z ,]+AGREEMENT",
        r"\n\s*FINANCING AGREEMENT\s*\n\s*This FINANCING AGREEMENT",
    ]
    for pattern in candidates:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.start()
    matches = list(ARTICLE_RE.finditer(text))
    if len(matches) > 1:
        return matches[1].start()
    return 0


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _looks_like_real_section_heading(raw_heading: str) -> bool:
    heading = raw_heading.strip()
    if heading.isdigit():
        return False
    if len(heading) > 1200:
        return False
    return bool(re.search(r"[A-Za-z]", heading))


def _section_heading(raw_heading: str) -> str:
    heading = compact_whitespace(raw_heading)
    return re.split(r"\s+\.\s+", heading, maxsplit=1)[0].strip(" .")


def _clause_heading(text: str) -> str | None:
    stripped = compact_whitespace(text)
    stripped = re.sub(r"^\([a-z]{1,2}\)\s+", "", stripped)
    if stripped.startswith("["):
        return stripped.split("]", maxsplit=1)[0].strip("[ ") or None
    if " . " in stripped[:120]:
        return stripped.split(" . ", maxsplit=1)[0].strip()
    sentence = stripped.split(".", maxsplit=1)[0].strip()
    return sentence[:100] if sentence else None


def _roman_subsegments(
    *,
    document_id: UUID,
    parent_id: UUID,
    parent_label: str,
    parent_text: str,
    start: int,
    end: int,
    first_order: int,
) -> list[SegmentDraft]:
    local = parent_text[start:end]
    matches = list(ROMAN_CLAUSE_RE.finditer(local))
    drafts: list[SegmentDraft] = []
    for index, match in enumerate(matches):
        roman_start = start + match.start()
        roman_end = start + matches[index + 1].start() if index + 1 < len(matches) else end
        label = f"{parent_label}({match.group(1)})"
        drafts.append(
            SegmentDraft(
                id=uuid.uuid4(),
                document_id=document_id,
                parent_id=parent_id,
                label=label,
                heading=_clause_heading(parent_text[roman_start:roman_end]),
                text=parent_text[roman_start:roman_end],
                char_start=roman_start,
                char_end=roman_end,
                order_index=first_order + index,
            )
        )
    return drafts


def _top_level_alpha_matches(section_text: str) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    expected_index = 0
    for match in ALPHA_CLAUSE_RE.finditer(section_text):
        expected = _alpha_label(expected_index)
        if match.group(1) == expected:
            matches.append(match)
            expected_index += 1
    return matches


def _alpha_label(index: int) -> str:
    if index < 26:
        return chr(ord("a") + index)
    doubled_index = index - 26
    if doubled_index < 26:
        return chr(ord("a") + doubled_index) * 2
    return chr(ord("a") + (doubled_index % 26)) * 3


def _containing_article(
    article_bounds: list[tuple[re.Match[str], int, int, UUID]], start: int
) -> tuple[re.Match[str], int, int, UUID] | None:
    for article in article_bounds:
        if article[1] <= start < article[2]:
            return article
    return None
