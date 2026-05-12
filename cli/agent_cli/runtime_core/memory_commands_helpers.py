from __future__ import annotations

from typing import Any, Dict, List, Optional


def positional_option_value(positionals: List[str], *, key: str) -> Optional[str]:
    option_name = f"--{key}"
    option_prefix = f"{option_name}="
    values = [str(item or "").strip() for item in list(positionals or [])]
    for index, token in enumerate(values):
        if token.startswith(option_prefix):
            value = token[len(option_prefix) :].strip()
            return value or None
        if token != option_name:
            continue
        if index + 1 >= len(values):
            return None
        next_value = values[index + 1].strip()
        if not next_value or next_value.startswith("--"):
            return None
        return next_value
    return None


def option_text(
    options: Dict[str, Any],
    positionals: List[str],
    *,
    key: str,
    default: str = "",
) -> str:
    raw_value = options.get(key)
    if raw_value is not None and not isinstance(raw_value, bool):
        text = str(raw_value).strip()
        if text:
            return text
    positional = positional_option_value(positionals, key=key)
    if positional:
        return positional
    return default


def trimmed(text: Any, *, max_chars: int = 200) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def render_memory_list(items: List[Dict[str, Any]]) -> str:
    lines = [f"memory_count={len(items)}"]
    for item in list(items or []):
        lines.append(
            f"- {item.get('memory_id') or '-'} | "
            f"type={item.get('memory_type') or '-'} | "
            f"status={item.get('status') or '-'} | "
            f"title={trimmed(item.get('title'), max_chars=60) or '-'}"
        )
    return "\n".join(lines)


def render_memory_show(item: Dict[str, Any]) -> str:
    tags = ",".join(str(tag) for tag in list(item.get("tags") or []) if str(tag).strip()) or "-"
    paths = ",".join(str(path) for path in list(item.get("paths") or []) if str(path).strip()) or "-"
    return (
        f"memory_id={item.get('memory_id') or '-'}\n"
        f"scope={item.get('scope') or '-'}\n"
        f"type={item.get('memory_type') or '-'}\n"
        f"status={item.get('status') or '-'}\n"
        f"title={item.get('title') or '-'}\n"
        f"summary={item.get('summary') or '-'}\n"
        f"tags={tags}\n"
        f"paths={paths}\n"
        f"hit_count={item.get('hit_count') or 0}\n"
        f"last_used_at={item.get('last_used_at') or '-'}"
    )


def render_recalled_memory_debug(runtime: Any, *, limit: int = 20) -> str:
    snapshot = dict(getattr(runtime, "_memory_context_snapshot", {}) or {})
    blocked_reason = str(snapshot.get("blocked_reason") or "").strip() or "-"
    query_paths = [
        str(item).strip()
        for item in list(snapshot.get("query_paths") or [])
        if str(item).strip()
    ]
    recalled_types = [
        str(item).strip()
        for item in list(snapshot.get("recalled_types") or [])
        if str(item).strip()
    ]
    ranking_items = [
        dict(item)
        for item in list(snapshot.get("ranking_explainability") or [])
        if isinstance(item, dict)
    ]
    recalled: List[Dict[str, Any]] = []
    for item in reversed(list(getattr(runtime, "reference_context_items", []) or [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("item_type") or "").strip() != "memory":
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        recalled.append(
            {
                "memory_id": str(metadata.get("memory_id") or "").strip() or str(item.get("path") or "").strip() or "-",
                "memory_type": str(metadata.get("memory_type") or "").strip() or "-",
                "score": metadata.get("score"),
                "reasons": list(metadata.get("reasons") or []),
            }
        )
        if len(recalled) >= max(1, limit):
            break
    recalled.reverse()
    lines = [
        f"recalled_memory_count={len(recalled)}",
        f"snapshot_recalled_count={int(snapshot.get('recalled_count') or 0)}",
        "snapshot_recalled_ids="
        + (
            ",".join(
                str(item).strip()
                for item in list(snapshot.get("recalled_ids") or [])
                if str(item).strip()
            )
            or "-"
        ),
        f"snapshot_blocked_reason={blocked_reason}",
        f"snapshot_query_paths={','.join(query_paths) or '-'}",
        f"snapshot_recalled_types={','.join(recalled_types) or '-'}",
        f"snapshot_ranking_explainability_count={len(ranking_items)}",
    ]
    for index, item in enumerate(ranking_items[: max(1, limit)], start=1):
        reasons = ",".join(
            str(reason).strip()
            for reason in list(item.get("reasons") or [])
            if str(reason).strip()
        ) or "-"
        rank = int(item.get("rank") or index)
        selected = "true" if bool(item.get("selected")) else "false"
        lines.append(
            f"# rank={rank} | memory_id={str(item.get('memory_id') or '-').strip() or '-'} | "
            f"type={str(item.get('memory_type') or '-').strip() or '-'} | "
            f"score={item.get('score') if item.get('score') is not None else '-'} | "
            f"selected={selected} | reasons={reasons}"
        )
    for entry in recalled:
        reasons_text = ",".join(str(reason) for reason in list(entry.get("reasons") or [])[:4]) or "-"
        lines.append(
            f"- {entry.get('memory_id') or '-'} | "
            f"type={entry.get('memory_type') or '-'} | "
            f"score={entry.get('score') if entry.get('score') is not None else '-'} | "
            f"reasons={reasons_text}"
        )
    return "\n".join(lines)
