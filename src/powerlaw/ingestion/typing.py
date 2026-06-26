import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DocumentTypeResult:
    title: str
    type: str
    execution_date: date | None
    confidence: float


TYPE_PATTERNS: list[tuple[str, str]] = [
    ("financing agreement", "financing_agreement"),
    ("membership interest purchase agreement", "mipa"),
    ("epc agreement", "epc"),
    ("engineering, procurement and construction", "epc"),
    ("tax equity ecca", "tax_equity_ecca"),
    ("equity capital contribution agreement", "tax_equity_ecca"),
    ("depositary agreement", "depositary"),
    ("accounts agreement", "accounts"),
    ("development services agreement", "dev_services"),
    ("articles of association", "articles"),
    ("warrant instrument", "warrant"),
    ("consent of independent registered public accounting firm", "auditor_consent"),
]


def classify_document(text: str) -> DocumentTypeResult:
    title = _extract_title(text)
    lowered = "\n".join(line.strip().lower() for line in text.splitlines()[:80])
    doc_type = "unknown"
    confidence = 0.45
    for phrase, candidate in TYPE_PATTERNS:
        if phrase in lowered:
            doc_type = candidate
            confidence = 0.93
            break
    return DocumentTypeResult(
        title=title,
        type=doc_type,
        execution_date=_extract_execution_date(text),
        confidence=confidence,
    )


def _extract_title(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "Untitled Document"
    if len(lines) >= 2 and set(lines[1]) <= {"="}:
        return lines[0]
    for line in lines[:80]:
        if line.isupper() and len(line) > 8 and not line.startswith("EXHIBIT"):
            return line.title()
    return lines[0]


def _extract_execution_date(text: str) -> date | None:
    match = re.search(
        r"(?:Dated as of|dated as of|dated)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        text[:5000],
    )
    if not match:
        match = re.search(r"\b([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b", text[:1500])
    if not match:
        return None
    parsed = re.match(r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", match.group(1))
    if parsed is None:
        return None
    month_name, day_text, year_text = parsed.groups()
    months = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    return date(int(year_text), months[month_name], int(day_text))
