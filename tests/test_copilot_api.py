from powerlaw.api.routes_copilot import _edit_operation, _unified_diff
from powerlaw.llm.client import extract_response_text
from powerlaw.main import create_app


def test_copilot_routes_are_registered() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])

    assert "/api/v1/copilot/identify-document" in paths
    assert "/api/v1/copilot/generate" in paths
    assert "/api/v1/copilot/edit-observations" in paths
    assert "/api/v1/copilot/document-edit-observations" in paths


def test_unified_diff_marks_before_and_after() -> None:
    diff = _unified_diff("Original clause", "Revised clause")

    assert "--- before" in diff
    assert "+++ after" in diff
    assert "-Original clause" in diff
    assert "+Revised clause" in diff


def test_edit_operation_marks_deletions() -> None:
    assert _edit_operation("Remove this generated clause.", "") == "deleted"
    assert _edit_operation("", "Add this document note.") == "inserted"
    assert _edit_operation("Old", "New") == "edited"


def test_extract_response_text_from_responses_payload() -> None:
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "Draft clause text."},
                ]
            }
        ]
    }

    assert extract_response_text(payload) == "Draft clause text."
