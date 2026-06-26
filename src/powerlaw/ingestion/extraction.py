from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

from powerlaw.ingestion.segmentation import SegmentDraft, compact_whitespace


@dataclass(frozen=True)
class ConditionDraft:
    id: UUID
    segment_id: UUID
    label: str
    trigger: str
    requirement_text: str
    discretionary: bool
    dating_rule: str | None
    waivable_by: str | None
    confidence: float
    beneficiary_name: str
    obligor_name: str

    def payload(
        self, beneficiary_party: UUID | None, obligor_party: UUID | None
    ) -> dict[str, object]:
        return {
            "id": self.id,
            "segment_id": self.segment_id,
            "beneficiary_party": beneficiary_party,
            "obligor_party": obligor_party,
            "trigger": self.trigger,
            "requirement_text": self.requirement_text,
            "discretionary": self.discretionary,
            "dating_rule": self.dating_rule,
            "status": "open",
            "waivable_by": self.waivable_by,
            "confidence": self.confidence,
            "verification_status": "unverified",
        }


def extract_article3_conditions(segments: list[SegmentDraft]) -> list[ConditionDraft]:
    conditions: list[ConditionDraft] = []
    for segment in segments:
        if not segment.label or not re.fullmatch(r"3\.[12]\([a-z]{1,2}\)", segment.label):
            continue
        requirement = compact_whitespace(segment.text)
        if "[ reserved" in requirement.lower() or "[reserved" in requirement.lower():
            continue
        trigger = "closing_date" if segment.label.startswith("3.1") else "each_credit_event"
        conditions.append(
            ConditionDraft(
                id=uuid.uuid4(),
                segment_id=segment.id,
                label=segment.label,
                trigger=trigger,
                requirement_text=requirement,
                discretionary=_is_discretionary(requirement),
                dating_rule=_dating_rule(requirement),
                waivable_by="Administrative Agent and the Lenders",
                confidence=_confidence(requirement),
                beneficiary_name="KEYBANK NATIONAL ASSOCIATION",
                obligor_name="Innovative Solar 31, LLC",
            )
        )
    return conditions


def infer_evidence_type(requirement_text: str) -> tuple[str, str]:
    lowered = requirement_text.lower()
    mapping = [
        ("opinion", "legal_opinion"),
        ("certificate", "certificate"),
        ("report", "consultant_report"),
        ("permit", "permit_or_approval"),
        ("approval", "permit_or_approval"),
        ("title policy", "title_policy"),
        ("survey", "survey"),
        ("ucc", "ucc_report"),
        ("financial statements", "financial_statement"),
        ("fees", "fee_payment"),
        ("taxes", "fee_payment"),
        ("consents and estoppels", "consent_or_estoppel"),
        ("notice of borrowing", "notice_of_borrowing"),
        ("drawdown certificate", "drawdown_certificate"),
        ("lien", "lien_release"),
        ("insurance", "insurance_evidence"),
    ]
    for needle, artifact_type in mapping:
        if needle in lowered:
            return artifact_type, f"Inferred from condition text containing '{needle}'."
    return "supporting_evidence", "Generic supporting evidence inferred from condition text."


def _is_discretionary(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "satisfactory to administrative agent",
            "acceptable to administrative agent",
            "administrative agent in its discretion",
            "in the judgment of administrative agent",
            "reasonably satisfactory",
            "reasonably acceptable",
        )
    )


def _dating_rule(text: str) -> str | None:
    lowered = text.lower()
    if "dated no earlier than ninety" in lowered or "not earlier than ninety" in lowered:
        return "not_earlier_than_90d"
    if "recent date" in lowered:
        return "recent_date"
    if "closing date" in lowered:
        return "as_of_closing"
    return None


def _confidence(text: str) -> float:
    if _is_discretionary(text):
        return 0.86
    if "shall have" in text.lower() or "delivery to" in text.lower():
        return 0.91
    return 0.82
