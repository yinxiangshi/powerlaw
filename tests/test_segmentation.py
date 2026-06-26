from pathlib import Path
from uuid import uuid4

from powerlaw.ingestion.extraction import extract_article3_conditions
from powerlaw.ingestion.segmentation import segment_document
from powerlaw.ingestion.typing import classify_document

FIXTURE = Path("data/exhibits/ex10-2.txt")


def test_financing_agreement_is_typed_from_content() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    result = classify_document(text)

    assert result.type == "financing_agreement"
    assert result.title == "NC-31 Financing Agreement (KeyBank Construction + ITC Bridge)"
    assert result.execution_date is not None


def test_article_three_conditions_have_source_spans() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    document_id = uuid4()
    segments = segment_document(text, document_id)
    conditions = extract_article3_conditions(segments)

    labels = {condition.label for condition in conditions}
    assert "3.1(a)" in labels
    assert "3.1(f)" in labels
    assert "3.2(g)" in labels
    assert "3.2(w)" in labels
    assert "3.1(x)" not in labels
    assert len(conditions) >= 45

    first = next(condition for condition in conditions if condition.label == "3.1(a)")
    segment = next(segment for segment in segments if segment.id == first.segment_id)
    assert segment.char_start < segment.char_end
    assert text[segment.char_start : segment.char_end] == segment.text
    assert first.trigger == "closing_date"
