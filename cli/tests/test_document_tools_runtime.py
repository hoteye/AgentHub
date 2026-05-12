from __future__ import annotations

import base64
from pathlib import Path

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import document_tools_runtime


_SAMPLE_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF9sAAAAASUVORK5CYII="
)


def _event_factory(name: str, ok: bool, summary: str, payload: dict) -> ToolEvent:
    return ToolEvent(name=name, ok=ok, summary=summary, payload=payload)


def test_view_document_returns_text_slice_payload(tmp_path: Path) -> None:
    doc = tmp_path / "notes.md"
    doc.write_text("alpha\nbeta\ngamma", encoding="utf-8")

    event = document_tools_runtime.view_document(
        path="notes.md",
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
        mode="text_slice",
        offset=6,
        max_chars=4,
    )

    assert event.ok is True
    assert event.name == "view_document"
    assert event.summary == "document text slice ready: notes.md"
    assert event.payload["source_mode"] == "tool_path"
    assert event.payload["capability_baseline"] == "extraction_only"
    assert event.payload["document_class"] == "text_like"
    assert event.payload["extraction_state"] == "text_slice_ready"
    assert event.payload["media_mode"] == "text_slice"
    assert event.payload["mime_type"] == "text/markdown"
    assert event.payload["structured_content"] is None
    assert event.payload["text_slice"]["text"] == "beta"
    assert event.payload["text_slice"]["offset"] == 6
    assert event.payload["text_slice"]["returned_chars"] == 4
    assert event.payload["text_slice"]["total_chars"] == 16
    assert event.payload["text_slice"]["truncated"] is True
    assert event.payload["text_slice"]["line_count"] == 1
    assert "image_artifacts" not in event.payload


def test_view_document_rejects_empty_path(tmp_path: Path) -> None:
    event = document_tools_runtime.view_document(
        path="",
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
    )

    assert event.ok is False
    assert event.summary == "view document failed"
    assert event.payload["document_class"] == "unknown"
    assert event.payload["extraction_state"] == "extraction_failed"
    assert event.payload["error_code"] == "invalid_path"
    assert event.payload["display_message"] == "Document path is required."


def test_view_document_reports_missing_file_as_fail_closed_unreadable_document(tmp_path: Path) -> None:
    event = document_tools_runtime.view_document(
        path="missing.md",
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
    )

    assert event.ok is False
    assert event.summary == "view document failed"
    assert event.payload["document_class"] == "unknown"
    assert event.payload["extraction_state"] == "extraction_failed"
    assert event.payload["error_code"] == "unreadable_document"
    assert "does not exist" in event.payload["display_message"]


def test_view_document_auto_returns_json_structured_content(tmp_path: Path) -> None:
    doc = tmp_path / "data.json"
    doc.write_text('{"name":"demo","count":2}', encoding="utf-8")

    event = document_tools_runtime.view_document(
        path=str(doc),
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
    )

    assert event.ok is True
    assert event.summary == "document structured content ready: data.json"
    assert event.payload["source_mode"] == "tool_path"
    assert event.payload["capability_baseline"] == "extraction_only"
    assert event.payload["document_class"] == "structured_json"
    assert event.payload["extraction_state"] == "structured_content_ready"
    assert event.payload["media_mode"] == "structured_content"
    assert event.payload["text_slice"] is None
    assert event.payload["structured_content"]["format"] == "json"
    assert event.payload["structured_content"]["data"] == {"name": "demo", "count": 2}


def test_view_document_reports_unreadable_document_after_probe(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    doc = tmp_path / "notes.md"
    doc.write_text("alpha\nbeta", encoding="utf-8")

    def denied(_: Path) -> bytes:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", denied)

    event = document_tools_runtime.view_document(
        path="notes.md",
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
    )

    assert event.ok is False
    assert event.summary == "view document failed"
    assert event.payload["document_class"] == "unknown"
    assert event.payload["extraction_state"] == "extraction_failed"
    assert event.payload["error_code"] == "unreadable_document"
    assert "permission denied" in event.payload["display_message"]


def test_view_document_structured_json_parse_error_fails_closed(tmp_path: Path) -> None:
    doc = tmp_path / "broken.json"
    doc.write_text('{"name":', encoding="utf-8")

    event = document_tools_runtime.view_document(
        path=str(doc),
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
        mode="structured_content",
    )

    assert event.ok is False
    assert event.summary == "view document failed"
    assert event.payload["document_class"] == "structured_json"
    assert event.payload["extraction_state"] == "extraction_failed"
    assert event.payload["error_code"] == "structured_parse_failed"
    assert event.payload["text_slice"] is None
    assert event.payload["structured_content"] is None


def test_view_document_fails_closed_for_images_without_image_injection(tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    image.write_bytes(_SAMPLE_PNG_BYTES)

    event = document_tools_runtime.view_document(
        path=str(image),
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
    )

    assert event.ok is False
    assert event.summary == "view document failed"
    assert event.payload["document_class"] == "image"
    assert event.payload["extraction_state"] == "unsupported_document_class"
    assert event.payload["error_code"] == "unsupported_media_mode"
    assert event.payload["media_mode"] == "unsupported_media"
    assert "image_artifacts" not in event.payload
    assert event.payload["media_probe"]["ok"] is True
    assert event.payload["media_probe"]["source"]["media_kind"] == "image"
    assert event.payload["media_probe"]["source"]["mime_type"] == "image/png"


def test_view_document_explicitly_fails_closed_for_pdf_baseline(tmp_path: Path) -> None:
    doc = tmp_path / "report.pdf"
    doc.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n")

    event = document_tools_runtime.view_document(
        path=str(doc),
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
    )

    assert event.ok is False
    assert event.summary == "view document failed"
    assert event.payload["document_class"] == "pdf"
    assert event.payload["extraction_state"] == "unsupported_document_class"
    assert event.payload["error_code"] == "unsupported_document_type"
    assert "TASK A baseline" in event.payload["display_message"]


def test_view_document_explicitly_fails_closed_for_notebook_baseline(tmp_path: Path) -> None:
    doc = tmp_path / "analysis.ipynb"
    doc.write_text('{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}', encoding="utf-8")

    event = document_tools_runtime.view_document(
        path=str(doc),
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
    )

    assert event.ok is False
    assert event.summary == "view document failed"
    assert event.payload["document_class"] == "notebook"
    assert event.payload["extraction_state"] == "unsupported_document_class"
    assert event.payload["error_code"] == "unsupported_document_type"
    assert "TASK A baseline" in event.payload["display_message"]


def test_view_document_fails_closed_for_binary_payload(tmp_path: Path) -> None:
    doc = tmp_path / "archive.bin"
    doc.write_bytes(b"\xff")

    event = document_tools_runtime.view_document(
        path=str(doc),
        workspace_root_factory=lambda: tmp_path,
        event_factory=_event_factory,
    )

    assert event.ok is False
    assert event.summary == "view document failed"
    assert event.payload["document_class"] == "binary"
    assert event.payload["extraction_state"] == "unsupported_document_class"
    assert event.payload["error_code"] == "unsupported_media_mode"
    assert event.payload["display_message"] == "Binary document extraction is not supported by view_document."
