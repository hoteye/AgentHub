from __future__ import annotations

import base64
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from shared.web_automation.snapshot import ensure_tab_snapshot_seed
from shared.web_automation.storage import STATE_DIR
from shared.web_automation.types import BrowserArtifact, BrowserTab

ARTIFACTS_DIR = STATE_DIR / "artifacts"
MAX_ARTIFACTS_PER_TAB = 20
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0L8AAAAASUVORK5CYII="
)


def emit_screenshot_artifact(tab: BrowserTab, *, ref: str | None = None) -> BrowserArtifact:
    ensure_tab_snapshot_seed(tab)
    out_path = create_artifact_path("screenshots", f"{tab.tab_id}-{uuid.uuid4().hex[:12]}.png")
    out_path.write_bytes(_PNG_1X1)
    return record_artifact(
        tab,
        kind="screenshot",
        path=out_path,
        content_type="image/png",
        size_bytes=out_path.stat().st_size,
        ref=ref,
    )


def emit_pdf_artifact(tab: BrowserTab) -> BrowserArtifact:
    ensure_tab_snapshot_seed(tab)
    out_path = create_artifact_path("pdf", f"{tab.tab_id}-{uuid.uuid4().hex[:12]}.pdf")
    out_path.write_bytes(_build_pdf_bytes(tab))
    return record_artifact(
        tab,
        kind="pdf",
        path=out_path,
        content_type="application/pdf",
        size_bytes=out_path.stat().st_size,
    )


def emit_download_artifact(
    tab: BrowserTab,
    *,
    ref: str,
    suggested_filename: str | None = None,
    requested_path: str | None = None,
) -> BrowserArtifact:
    ensure_tab_snapshot_seed(tab)
    safe_name = sanitize_artifact_filename(suggested_filename or f"{ref}.bin", default="download.bin")
    out_path = (
        resolve_artifact_output_path("downloads", requested_path)
        if str(requested_path or "").strip()
        else create_artifact_path("downloads", f"{tab.tab_id}-{uuid.uuid4().hex[:12]}-{safe_name}")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(f"Synthetic download for {ref} from {tab.url}\n".encode("utf-8"))
    content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return record_artifact(
        tab,
        kind="download",
        path=out_path,
        content_type=content_type,
        size_bytes=out_path.stat().st_size,
        ref=ref,
        suggested_filename=safe_name,
    )


def emit_waited_download_artifact(
    tab: BrowserTab,
    *,
    suggested_filename: str | None = None,
    requested_path: str | None = None,
) -> BrowserArtifact:
    ensure_tab_snapshot_seed(tab)
    safe_name = sanitize_artifact_filename(suggested_filename or "download.bin", default="download.bin")
    out_path = (
        resolve_artifact_output_path("downloads", requested_path)
        if str(requested_path or "").strip()
        else create_artifact_path("downloads", f"{tab.tab_id}-{uuid.uuid4().hex[:12]}-{safe_name}")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(f"Synthetic waited download from {tab.url}\n".encode("utf-8"))
    content_type = mimetypes.guess_type(out_path.name)[0] or "application/octet-stream"
    return record_artifact(
        tab,
        kind="download",
        path=out_path,
        content_type=content_type,
        size_bytes=out_path.stat().st_size,
        suggested_filename=safe_name,
    )


def record_artifact(
    tab: BrowserTab,
    *,
    kind: str,
    path: Path,
    content_type: str,
    size_bytes: int,
    ref: str | None = None,
    url: str | None = None,
    title: str | None = None,
    suggested_filename: str | None = None,
) -> BrowserArtifact:
    artifact = BrowserArtifact(
        artifact_id=uuid.uuid4().hex,
        kind=kind,
        path=str(path.resolve()),
        content_type=content_type,
        size_bytes=int(size_bytes),
        created_at=_timestamp(),
        target_id=tab.tab_id,
        url=str(url or tab.url),
        title=str(title or tab.title),
        ref=str(ref).strip() or None if ref is not None else None,
        suggested_filename=str(suggested_filename).strip() or None if suggested_filename is not None else None,
    )
    tab.artifacts.append(artifact)
    if len(tab.artifacts) > MAX_ARTIFACTS_PER_TAB:
        del tab.artifacts[:-MAX_ARTIFACTS_PER_TAB]
    return artifact


def create_artifact_path(kind_dir: str, file_name: str) -> Path:
    root = (ARTIFACTS_DIR / kind_dir)
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    candidate = (root / file_name).resolve()
    if resolved_root != candidate.parent:
        raise ValueError("artifact path escaped runtime directory")
    return candidate


def resolve_artifact_output_path(kind_dir: str, requested_path: str) -> Path:
    root = (ARTIFACTS_DIR / kind_dir)
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    normalized = str(requested_path or "").strip().replace("\\", "/")
    relative = Path(normalized)
    if not str(relative).strip():
        raise ValueError("artifact output path is required")
    if relative.is_absolute():
        raise ValueError("artifact path must be relative to runtime directory")
    _validate_artifact_relative_path(relative)
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("artifact path escaped runtime directory") from exc
    return candidate


def resolve_existing_artifact_path(raw_path: str) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        raise ValueError("artifact path is required")
    candidate = Path(text)
    if not candidate.is_absolute():
        raise ValueError("artifact path must be absolute")
    resolved_root = ARTIFACTS_DIR.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("artifact path is outside runtime artifacts directory") from exc
    if not resolved_candidate.is_file():
        raise ValueError("artifact file not found")
    return resolved_candidate


def sanitize_artifact_filename(file_name: str, *, default: str = "artifact.bin") -> str:
    text = str(file_name or "").strip().replace("\\", "/")
    text = text.split("/")[-1]
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("._-")
    if not text:
        return default
    if _is_reserved_artifact_segment(text):
        return f"file-{text}"
    return text


def _validate_artifact_relative_path(relative: Path) -> None:
    for segment in relative.parts:
        text = str(segment or "").strip()
        if not text or text in {".", ".."}:
            raise ValueError("artifact path escaped runtime directory")
        if _is_reserved_artifact_segment(text):
            raise ValueError("artifact path contains reserved file name")


def _is_reserved_artifact_segment(segment: str) -> bool:
    base_name = str(segment or "").split(".")[0].strip().upper()
    return bool(base_name) and base_name in _WINDOWS_RESERVED_NAMES


def _build_pdf_bytes(tab: BrowserTab) -> bytes:
    lines = [
        "Synthetic browser export",
        f"Target: {tab.tab_id}",
        f"Profile: {tab.profile}",
        f"Title: {tab.title}",
        f"URL: {tab.url}",
        "",
    ]
    lines.extend(tab.text.splitlines()[:24])
    content_lines = ["BT", "/F1 12 Tf", "50 760 Td"]
    for index, raw_line in enumerate(lines):
        if index > 0:
            content_lines.append("0 -16 Td")
        content_lines.append(f"({_escape_pdf_text(raw_line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _escape_pdf_text(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
