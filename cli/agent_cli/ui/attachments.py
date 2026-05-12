from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlparse

from cli.agent_cli.models import PromptAttachment


def normalize_single_pasted_path(
    value: str,
    *,
    windows_drive_re,
    windows_unc_re,
) -> str | None:
    candidate = str(value or "").strip()
    if not candidate:
        return None
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {'"', "'"}:
        candidate = candidate[1:-1].strip()
    if not candidate:
        return None

    lower = candidate.lower()
    if lower.startswith("file://"):
        parsed = urlparse(candidate)
        if parsed.scheme.lower() != "file":
            return None
        path_text = unquote(parsed.path or "")
        netloc = unquote(parsed.netloc or "")
        if netloc and netloc.lower() != "localhost":
            windows_path = path_text.replace("/", "\\")
            candidate = f"\\\\{netloc}{windows_path}"
        else:
            candidate = path_text
        if re.match(r"^/[A-Za-z]:", candidate):
            candidate = candidate[1:]

    if windows_drive_re.match(candidate):
        normalized_candidate = candidate.replace("/", "\\")
        return str(PureWindowsPath(normalized_candidate))

    if windows_unc_re.match(candidate):
        return candidate.replace("/", "\\")

    path = Path(candidate)
    try:
        if path.is_absolute() or path.exists():
            return str(path.resolve(strict=False))
    except (OSError, ValueError):
        return None
    return None


def format_pasted_path(path_text: str) -> str:
    text = str(path_text or "")
    if re.search(r"\s", text):
        return f'"{text}"'
    return text


def format_attachment_reference(path_text: str) -> str:
    return f"@{format_pasted_path(path_text)}"


def normalize_pasted_path_text(
    text: str,
    *,
    windows_drive_re,
    windows_unc_re,
) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    stripped = normalized.strip()
    if not stripped:
        return normalized

    # Keep pasted text literal. Attachment references use explicit `@...` syntax
    # at submission time, and slash commands keep `/...` semantics while editing.
    return normalized


def extract_attachment_references(
    text: str,
    *,
    windows_drive_re,
    windows_unc_re,
) -> tuple[str, list[PromptAttachment]]:
    content = str(text or "")
    attachments: list[PromptAttachment] = []
    seen_paths: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        candidate = next(
            (
                group
                for group in match.groups()
                if group is not None and str(group).strip()
            ),
            "",
        )
        normalized = normalize_single_pasted_path(
            candidate,
            windows_drive_re=windows_drive_re,
            windows_unc_re=windows_unc_re,
        )
        if normalized is None:
            return match.group(0)
        if normalized not in seen_paths:
            seen_paths.add(normalized)
            attachments.append(PromptAttachment.from_path(normalized, source="composer_file_reference"))
        return format_pasted_path(normalized)

    return (
        re.sub(r"(?<!\S)@(?:\"([^\"]+)\"|'([^']+)'|(\S+))", replace, content),
        attachments,
    )
