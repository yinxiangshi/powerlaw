from pathlib import Path
from uuid import uuid4

from powerlaw.ingestion.extraction import extract_article3_conditions
from powerlaw.ingestion.linking import resolve_condition_cross_refs
from powerlaw.ingestion.segmentation import segment_document


def test_condition_cross_references_resolve_to_segments() -> None:
    text = Path("data/exhibits/ex10-2.txt").read_text(encoding="utf-8")
    segments = segment_document(text, uuid4())
    conditions = extract_article3_conditions(segments)

    cross_refs, dependencies, unresolved = resolve_condition_cross_refs(
        conditions=conditions,
        segments=segments,
    )

    assert any(ref.to_label == "3.1(f)" and ref.resolved for ref in cross_refs)
    assert any(ref.to_label == "3.2" and ref.resolved for ref in cross_refs)
    assert dependencies
    assert not any("3.1(f)" in item for item in unresolved)
