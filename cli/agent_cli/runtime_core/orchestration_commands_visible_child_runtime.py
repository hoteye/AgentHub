from __future__ import annotations

import time
from typing import Any
from uuid import uuid4


def _visible_child_backend(runtime: Any) -> Any:
    backend = getattr(runtime, "visible_child_tab_backend", None)
    if backend is None:
        raise ValueError("visible child tab backend is not available")
    return backend


def _child_ids(backend: Any, parent_tab_id: str) -> list[str]:
    child_ids_fn = getattr(backend, "child_tab_ids", None)
    if not callable(child_ids_fn):
        return []
    return [
        str(item).strip() for item in list(child_ids_fn(parent_tab_id) or []) if str(item).strip()
    ]


def _resolve_tab_selector(backend: Any, selector: str, *, default: str = "") -> str:
    normalized = str(selector or "").strip()
    if not normalized:
        return default
    if normalized.lower() in {"active", "current"}:
        return str(getattr(backend, "active_tab_id", "") or default).strip()
    tabs = getattr(backend, "_tabs", None)
    if isinstance(tabs, dict) and normalized in tabs:
        return normalized
    display_label = getattr(backend, "display_tab_label", None)
    tab_order = list(getattr(backend, "_tab_order", []) or [])
    if callable(display_label):
        for tab_id in tab_order:
            try:
                if str(display_label(tab_id)).strip().lower() == normalized.lower():
                    return str(tab_id)
            except Exception:
                continue
    return normalized


def _parent_tab_id(runtime: Any, backend: Any, selector: str = "") -> str:
    default = str(getattr(runtime, "visible_child_parent_tab_id", "") or "").strip()
    if not default:
        default = str(getattr(backend, "active_tab_id", "") or "").strip()
    parent_tab_id = _resolve_tab_selector(backend, selector, default=default)
    if not parent_tab_id:
        raise ValueError("visible child parent tab is not available")
    return parent_tab_id


def _resolve_child_target(backend: Any, parent_tab_id: str, selector: str) -> str:
    normalized = str(selector or "").strip()
    child_ids = _child_ids(backend, parent_tab_id)
    if normalized.lower() in {"latest", "last", ""}:
        return child_ids[-1] if child_ids else ""
    tab_id = _resolve_tab_selector(backend, normalized)
    if tab_id in child_ids:
        return tab_id
    raise ValueError(f"unknown visible child tab: {selector}")


def _metadata_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _run_spawn_child_tab_request(runtime: Any, request: dict[str, Any]) -> dict[str, Any]:
    task_text = str(
        request.get("task") or request.get("message") or request.get("prompt") or ""
    ).strip()
    if not task_text:
        raise ValueError("__spawn_child_tab requires task")
    backend = _visible_child_backend(runtime)
    parent_tab_id = _parent_tab_id(runtime, backend, str(request.get("parent") or ""))
    metadata = _metadata_payload(request)
    metadata.setdefault(
        "run_id",
        str(request.get("run_id") or metadata.get("run_id") or f"visible_{uuid4().hex[:12]}"),
    )
    task_name = str(
        request.get("task_name") or request.get("label") or metadata.get("card_id") or ""
    ).strip()
    if task_name:
        metadata["card_id"] = task_name
    metadata.setdefault("source", "spawn_child_tab")
    dispatcher = getattr(backend, "dispatch_visible_child_task", None)
    if not callable(dispatcher):
        raise ValueError("visible child tab dispatcher is not available")
    result = dict(
        dispatcher(
            parent_tab_id=parent_tab_id,
            task_text=task_text,
            metadata=metadata,
        )
    )
    result["parent_tab_id"] = parent_tab_id
    result["task_name"] = task_name
    return result


def _run_send_child_tab_request(runtime: Any, request: dict[str, Any]) -> dict[str, Any]:
    target = str(request.get("target") or request.get("tab_id") or request.get("id") or "").strip()
    message = str(
        request.get("message") or request.get("task") or request.get("prompt") or ""
    ).strip()
    if not target:
        raise ValueError("__send_child_tab requires target")
    if not message:
        raise ValueError("__send_child_tab requires message")
    backend = _visible_child_backend(runtime)
    parent_tab_id = _parent_tab_id(runtime, backend, str(request.get("parent") or ""))
    child_tab_id = _resolve_child_target(backend, parent_tab_id, target)
    if not child_tab_id:
        raise ValueError("no visible child tabs are available")
    sender = getattr(backend, "send_visible_child_task", None)
    if not callable(sender):
        raise ValueError("visible child tab sender is not available")
    metadata = _metadata_payload(request)
    run_id = str(request.get("run_id") or metadata.get("run_id") or "").strip()
    card_id = str(
        request.get("task_name")
        or request.get("card_id")
        or request.get("label")
        or metadata.get("card_id")
        or ""
    ).strip()
    if run_id:
        metadata["run_id"] = run_id
    if card_id:
        metadata["card_id"] = card_id
    if run_id or card_id:
        metadata.setdefault(
            "orchestration",
            {
                "run_id": run_id,
                "card_id": card_id,
                "attempt": int(metadata.get("attempt") or 0),
            },
        )
    metadata.setdefault("source", "send_child_tab")
    return dict(
        sender(
            parent_tab_id=parent_tab_id,
            child_tab_id=child_tab_id,
            task_text=message,
            interrupt=bool(request.get("interrupt")),
            metadata=metadata,
        )
    )


def _snapshot_matches(
    snapshot: dict[str, Any],
    *,
    targets: set[str],
    backend: Any,
) -> bool:
    if not targets:
        return True
    values = {
        str(snapshot.get("tab_id") or "").strip(),
        str(snapshot.get("run_id") or "").strip(),
    }
    assignment = snapshot.get("assignment_ref")
    if isinstance(assignment, dict):
        run_id = str(assignment.get("run_id") or "").strip()
        card_id = str(assignment.get("card_id") or "").strip()
        attempt = str(assignment.get("attempt") or "0").strip() or "0"
        values.update({run_id, card_id})
        if run_id or card_id:
            values.add(f"{run_id}:{card_id}:{attempt}")
    display_label = getattr(backend, "display_tab_label", None)
    if callable(display_label):
        try:
            values.add(str(display_label(str(snapshot.get("tab_id") or ""))).strip())
        except Exception:
            pass
    return bool({value.lower() for value in values if value} & targets)


def _snapshot_tab_id(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("tab_id") or "").strip().lower()


def _snapshot_run_id(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("run_id") or "").strip()


def _snapshot_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _snapshot_run_serial(snapshot: dict[str, Any]) -> int:
    run_id = _snapshot_run_id(snapshot)
    if "-run-" not in run_id:
        return -1
    suffix = run_id.rsplit("-run-", 1)[-1].strip()
    return int(suffix) if suffix.isdigit() else -1


def _snapshot_sort_key(snapshot: dict[str, Any]) -> tuple[int, float, float]:
    return (
        _snapshot_run_serial(snapshot),
        _snapshot_float(snapshot.get("started_at")),
        _snapshot_float(snapshot.get("finished_at")),
    )


def _terminal_snapshot(snapshot: dict[str, Any]) -> bool:
    return str(snapshot.get("terminal_state") or "").strip().lower() in {
        "completed",
        "failed",
        "interrupted",
        "cancelled",
        "timed_out",
        "unknown",
    }


def _raw_visible_child_snapshots(
    *,
    backend: Any,
    parent_tab_id: str,
) -> list[dict[str, Any]]:
    snapshot_fn = getattr(backend, "visible_child_task_run_snapshots", None)
    if not callable(snapshot_fn):
        return []
    return [dict(item) for item in list(snapshot_fn(parent_tab_id) or []) if isinstance(item, dict)]


def _resolve_wait_targets(
    *,
    backend: Any,
    parent_tab_id: str,
    raw_targets: list[Any],
    include_all: bool,
) -> tuple[set[str], set[str]]:
    child_ids = _child_ids(backend, parent_tab_id)
    if include_all or not raw_targets:
        return ({item.lower() for item in child_ids if item}, set())
    tab_targets: set[str] = set()
    direct_targets: set[str] = set()
    for raw in raw_targets:
        text = str(raw or "").strip()
        if not text:
            continue
        if text.lower() in {"latest", "last"}:
            resolved_latest = child_ids[-1] if child_ids else ""
            if resolved_latest:
                tab_targets.add(resolved_latest.lower())
            continue
        resolved = _resolve_tab_selector(backend, text)
        if resolved in child_ids:
            tab_targets.add(resolved.lower())
            continue
        direct_targets.add(text.lower())
    return tab_targets, direct_targets


def _dedupe_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for snapshot in snapshots:
        key = (_snapshot_tab_id(snapshot), _snapshot_run_id(snapshot).lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(snapshot)
    return result


def _selected_wait_snapshots(
    *,
    backend: Any,
    parent_tab_id: str,
    tab_targets: set[str],
    direct_targets: set[str],
) -> list[dict[str, Any]]:
    snapshots = _raw_visible_child_snapshots(backend=backend, parent_tab_id=parent_tab_id)
    selected: list[dict[str, Any]] = []
    for tab_id in sorted(tab_targets):
        candidates = [item for item in snapshots if _snapshot_tab_id(item) == tab_id]
        if candidates:
            selected.append(max(candidates, key=_snapshot_sort_key))
    if direct_targets:
        selected.extend(
            item
            for item in snapshots
            if _snapshot_matches(item, targets=direct_targets, backend=backend)
        )
    return _dedupe_snapshots(selected)


def _wait_condition_met(
    snapshots: list[dict[str, Any]],
    *,
    wait_for: str,
) -> bool:
    if not snapshots:
        return False
    terminal = [item for item in snapshots if _terminal_snapshot(item)]
    if wait_for == "any":
        return bool(terminal)
    return bool(snapshots) and len(terminal) == len(snapshots)


def _normalize_wait_for(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"any", "first", "one"}:
        return "any"
    return "all"


def _run_wait_child_tasks_request(runtime: Any, request: dict[str, Any]) -> dict[str, Any]:
    backend = _visible_child_backend(runtime)
    parent_tab_id = _parent_tab_id(runtime, backend, str(request.get("parent") or ""))
    raw_targets = request.get("targets")
    if raw_targets is None:
        raw_target = str(
            request.get("target") or request.get("tab_id") or request.get("id") or ""
        ).strip()
        raw_targets = [raw_target] if raw_target else []
    if isinstance(raw_targets, list | tuple):
        raw_target_list = list(raw_targets or [])
    else:
        raw_target_list = []
    include_all = bool(request.get("include_all"))
    tab_targets, direct_targets = _resolve_wait_targets(
        backend=backend,
        parent_tab_id=parent_tab_id,
        raw_targets=raw_target_list,
        include_all=include_all,
    )
    targets = tab_targets | direct_targets
    terminal_only = bool(request.get("terminal_only"))
    wait_for = _normalize_wait_for(request.get("wait_for"))
    try:
        timeout_ms = max(0, min(300_000, int(request.get("timeout_ms") or 0)))
    except (TypeError, ValueError):
        timeout_ms = 0
    deadline = time.monotonic() + (timeout_ms / 1000)
    timed_out = False
    snapshots = _selected_wait_snapshots(
        backend=backend,
        parent_tab_id=parent_tab_id,
        tab_targets=tab_targets,
        direct_targets=direct_targets,
    )
    condition_met = _wait_condition_met(snapshots, wait_for=wait_for)
    if timeout_ms == 0 and "timeout_ms" in request and not condition_met:
        timed_out = True
    while timeout_ms > 0 and not condition_met:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        time.sleep(0.1)
        snapshots = _selected_wait_snapshots(
            backend=backend,
            parent_tab_id=parent_tab_id,
            tab_targets=tab_targets,
            direct_targets=direct_targets,
        )
        condition_met = _wait_condition_met(snapshots, wait_for=wait_for)
    returned_snapshots = (
        [item for item in snapshots if _terminal_snapshot(item)] if terminal_only else snapshots
    )
    terminal_count = len([item for item in snapshots if _terminal_snapshot(item)])
    return {
        "parent_tab_id": parent_tab_id,
        "child_count": len(_child_ids(backend, parent_tab_id)),
        "targets": sorted(targets),
        "wait_for": wait_for,
        "task_runs": returned_snapshots,
        "selected_task_run_ids": [
            _snapshot_run_id(item) for item in snapshots if _snapshot_run_id(item)
        ],
        "pending_count": max(0, len(snapshots) - terminal_count),
        "terminal_count": terminal_count,
        "timed_out": timed_out,
    }
