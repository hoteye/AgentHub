from __future__ import annotations

import re


def detail_segments(raw: str) -> list[str]:
    segments: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if " | " in line:
            segments.extend(part.strip() for part in line.split(" | ") if part.strip())
            continue
        segments.append(line)
    return segments


def format_transcript_block_lines(
    content: str,
    *,
    first_prefix: str,
    continuation_prefix: str,
) -> list[str]:
    raw_lines = (content or "").splitlines() or [""]
    return [
        f"{first_prefix if index == 0 else continuation_prefix}{raw_line}"
        for index, raw_line in enumerate(raw_lines)
    ]


def format_activity_detail_lines(detail: str, *, stream: str = "stdout") -> list[str]:
    raw_lines = [line.rstrip() for line in detail.splitlines() if line.strip()]
    if not raw_lines:
        return []
    if stream and stream != "stdout":
        first, *rest = raw_lines
        return [f"  └ {stream}: {first}", *(f"    {line}" for line in rest)]
    first, *rest = raw_lines
    return [f"  └ {first}", *(f"    {line}" for line in rest)]


def is_approval_request_fallback_text(text: str) -> bool:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return False
    first = lines[0].lower()
    has_decision_command = any(line.startswith(("/approve ", "/reject ")) for line in lines)
    has_approval_id = any(
        line.startswith(("approval_id=", "已提交命令审批：", "已提交补丁审批："))
        for line in lines
    )
    request_prefixes = (
        "已提交命令审批",
        "已提交补丁审批",
        "已提交后台 teammate 审批",
        "request shell approval",
        "request patch approval",
    )
    if not any(first.startswith(prefix.lower()) for prefix in request_prefixes):
        return False
    return has_decision_command or has_approval_id or len(lines) == 1


def strip_activity_prefix(title: str, prefix: str) -> str:
    stripped = title.strip()
    if stripped.lower().startswith(prefix.lower()):
        return stripped[len(prefix) :].strip()
    return stripped


def detail_lookup(raw: str, *keys: str) -> str:
    values: dict[str, str] = {}
    for line in detail_segments(raw):
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key_text = key.strip().lower()
        value_text = value.strip()
        if key_text and value_text and key_text not in values:
            values[key_text] = value_text
    for key in keys:
        value = values.get(str(key).strip().lower(), "")
        if value:
            return value
    return ""


def activity_param_text(params: dict[str, object], detail: str, *keys: str) -> str:
    for key in keys:
        value = params.get(str(key))
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return detail_lookup(detail, *keys)


def activity_param_only_text(params: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = params.get(str(key))
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def read_subject(raw: str) -> str:
    detail_subject = detail_lookup(raw, "file_path", "path")
    if detail_subject:
        return detail_subject
    segments = [segment.strip() for segment in raw.split(" | ") if segment.strip()]
    if segments:
        return segments[0]
    return ""


def search_subject(query: str, path: str) -> str:
    normalized_query = str(query or "").strip()
    normalized_path = str(path or "").strip()
    if normalized_query and normalized_path:
        return f"{normalized_query} in {normalized_path}"
    return normalized_query or normalized_path


def search_subject_from_detail(raw: str) -> str:
    return search_subject(
        detail_lookup(raw, "query", "pattern"),
        detail_lookup(raw, "path", "dir_path"),
    )


def format_exploration_detail_item(detail: tuple[str, str]) -> str:
    kind, subject = detail
    normalized_subject = str(subject or "").strip()
    if kind == "list":
        return f"List {normalized_subject or '.'}".strip()
    if kind == "search":
        return f"Search {normalized_subject}".strip()
    if kind == "read":
        return f"Read {normalized_subject}".strip()
    return normalized_subject


def parse_exploration_detail_item(text: str) -> tuple[str, str] | None:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    lowered = stripped.lower()
    if lowered.startswith("list "):
        return ("list", stripped[5:].strip() or ".")
    if lowered.startswith("search "):
        subject = stripped[7:].strip()
        return ("search", subject) if subject else None
    if lowered.startswith("read "):
        subject = stripped[5:].strip()
        return ("read", subject) if subject else None
    return None


def merge_exploration_detail_items(
    details: list[tuple[str, str]],
    detail: tuple[str, str],
) -> list[tuple[str, str]]:
    kind, subject = detail
    normalized_subject = str(subject or "").strip()
    if kind == "list":
        normalized_detail = ("list", normalized_subject or ".")
    else:
        if not normalized_subject:
            return list(details)
        normalized_detail = (kind, normalized_subject)
    if normalized_detail in details:
        return list(details)
    next_details = list(details)
    if normalized_detail[0] == "read" and next_details and next_details[-1][0] == "read":
        existing_names = [item.strip() for item in next_details[-1][1].split(",") if item.strip()]
        if normalized_detail[1] and normalized_detail[1] not in existing_names:
            next_details[-1] = ("read", ", ".join([*existing_names, normalized_detail[1]]))
        return next_details
    next_details.append(normalized_detail)
    return next_details


def render_exploration_entry_lines(details: list[tuple[str, str]], *, status: str) -> list[str]:
    rendered_details = [format_exploration_detail_item(detail) for detail in details]
    rendered_details = [item for item in rendered_details if item]
    if not rendered_details:
        return []
    header = "• Exploring" if status == "running" else "• Explored"
    first_detail, *rest_details = rendered_details
    return [header, f"  └ {first_detail}", *(f"    {detail}" for detail in rest_details)]


def compact_web_domains(value: str, *, limit: int = 3) -> str:
    domains = [item.strip() for item in value.split(",") if item.strip()]
    if len(domains) <= limit:
        return ", ".join(domains)
    return ", ".join(domains[:limit]) + f" +{len(domains) - limit}"


def format_ranked_web_result(result: str) -> str:
    match = re.match(r"^(\d+\.)\s+(.*)$", str(result or "").strip())
    if not match:
        return str(result or "").strip()
    rank = match.group(1)
    remainder = match.group(2).strip()
    segments = [segment.strip() for segment in remainder.split(" | ") if segment.strip()]
    if len(segments) >= 3:
        return f"{rank} {segments[-1]}"
    return f"{rank} {remainder}".strip()
