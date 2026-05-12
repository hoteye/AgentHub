from __future__ import annotations

from typing import Any, Callable


def preview_text(value: Any, *, max_chars: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def parse_csv_paths(value: Any) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    items = [segment.strip() for segment in raw.split(",")]
    seen: set[str] = set()
    resolved: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        resolved.append(item)
    return resolved


def parse_positive_float(value: Any, *, option_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {option_name}: {value}") from exc
    if parsed <= 0:
        raise ValueError(f"invalid {option_name}: {value}")
    return parsed


def background_task_lines(
    items: list[Any],
    *,
    get_status_fn: Callable[[str], Any] | None,
    overview_line_fn: Callable[..., str],
    preview_text_fn: Callable[..., str],
) -> list[str]:
    item_lines: list[str] = []
    for item in items:
        task_id = str(getattr(item, "task_id", "") or "")
        status_payload = get_status_fn(task_id) if callable(get_status_fn) else None
        item_lines.append(
            overview_line_fn(
                item,
                status_payload=status_payload,
                preview_text_fn=preview_text_fn,
            )
        )
    return item_lines


def delegated_workflow_projection(
    items: list[dict[str, Any]],
    *,
    limit: int,
    delegated_workflow_line_fn: Callable[..., tuple[str, str | None]],
    preview_text_fn: Callable[..., str],
) -> tuple[list[str], set[str]]:
    lines: list[str] = []
    mirrored_task_ids: set[str] = set()
    for payload in items[: max(1, int(limit))]:
        agent_id = str(payload.get("agent_id") or "").strip()
        if not agent_id:
            continue
        line, mirrored_task_id = delegated_workflow_line_fn(
            payload,
            preview_text_fn=preview_text_fn,
        )
        lines.append(line)
        if mirrored_task_id:
            mirrored_task_ids.add(mirrored_task_id)
    return lines, mirrored_task_ids


def background_workflow_projection(
    items: list[Any],
    *,
    limit: int,
    mirrored_task_ids: set[str],
    background_workflow_line_fn: Callable[..., str],
    preview_text_fn: Callable[..., str],
) -> tuple[list[str], int]:
    lines: list[str] = []
    mirrored_count = 0
    for item in items:
        task_id = str(getattr(item, "task_id", "") or "").strip()
        if task_id in mirrored_task_ids:
            mirrored_count += 1
            continue
        lines.append(
            background_workflow_line_fn(
                item,
                preview_text_fn=preview_text_fn,
            )
        )
        if len(lines) >= max(1, int(limit)):
            break
    return lines, mirrored_count


def benchmark_enqueue_payload(argv: list[str], timeout_payload: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    return (
        {
            "argv": argv,
            **timeout_payload,
        },
        [
            ("argv", argv if argv else None),
            ("timeout_seconds", timeout_payload.get("timeout_seconds")),
        ],
    )


def smoke_enqueue_payload(
    *,
    kind: str,
    forwarded: list[str],
    runtime_cwd: str,
    timeout_payload: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    return (
        {
            "kind": kind,
            "argv": forwarded,
            "cwd": runtime_cwd,
            **timeout_payload,
        },
        [
            ("kind", kind),
            ("argv", forwarded if forwarded else None),
            ("timeout_seconds", timeout_payload.get("timeout_seconds")),
        ],
    )


def task_payload_text(
    payload: Any,
    *,
    task_id: str,
    not_found_text: str,
    no_review_text: str | None = None,
    text_fn: Callable[..., str],
) -> str:
    if not isinstance(payload, dict):
        return not_found_text
    if no_review_text is not None:
        artifact = dict(payload.get("artifact") or {})
        if not artifact.get("staged_workspace"):
            return no_review_text
    return text_fn(payload, task_id=task_id)
