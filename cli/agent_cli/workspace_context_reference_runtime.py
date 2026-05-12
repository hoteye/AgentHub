from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from cli.agent_cli import workspace_context_reference_projection_runtime as workspace_context_reference_projection_runtime_helpers


def _doc_kind_for_path(path_text: str) -> str:
    normalized = str(path_text or "").replace("\\", "/").lower()
    if "/.agenthub/rules/" in normalized:
        return "rule"
    return "doc"


def _default_instruction_sources(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for order, item in enumerate(list(docs or []), start=1):
        path = str(item.get("path") or "").strip().replace("\\", "/")
        if not path:
            continue
        sources.append(
            {
                "path": path,
                "kind": _doc_kind_for_path(path),
                "scope": "project",
                "order": order,
            }
        )
    return sources


def _normalized_instruction_sources(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().replace("\\", "/")
        if not path or path in seen:
            continue
        seen.add(path)
        kind = str(item.get("kind") or "").strip().lower() or _doc_kind_for_path(path)
        if kind not in {"doc", "rule", "unknown"}:
            kind = "unknown"
        scope = str(item.get("scope") or "").strip().lower() or "project"
        try:
            order = int(item.get("order"))
        except (TypeError, ValueError):
            order = index
        normalized.append(
            {
                "path": path,
                "kind": kind,
                "scope": scope,
                "order": max(1, order),
            }
        )
    return sorted(normalized, key=lambda item: (int(item.get("order") or 0), str(item.get("path") or "")))


def _rule_paths_from_sources(sources: List[Dict[str, Any]]) -> List[str]:
    paths = [
        str(item.get("path") or "").strip()
        for item in list(sources or [])
        if str(item.get("kind") or "").strip().lower() == "rule" and str(item.get("path") or "").strip()
    ]
    return sorted(set(paths))


def workspace_contract(snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(snapshot or {})
    docs = [
        {
            "path": str(item.get("path") or "").strip(),
            "size": int(item.get("size") or 0),
            "mtime_ns": int(item.get("mtime_ns") or 0),
            "content_digest": str(item.get("content_digest") or "").strip(),
        }
        for item in list(payload.get("docs") or [])
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    skills = [
        {
            "name": str(item.get("name") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "path": str(item.get("path") or "").strip(),
        }
        for item in list(payload.get("skills") or [])
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    contract = {
        "cwd": str(payload.get("cwd") or "").strip(),
        "workspace_root": str(payload.get("workspace_root") or "").strip(),
        "trust_level": str(payload.get("trust_level") or "").strip(),
        "instructions_digest": str(payload.get("instructions_digest") or "").strip(),
        "docs": docs,
        "skills": skills,
        "instruction_sources": _normalized_instruction_sources(payload.get("instruction_sources")),
        "rule_paths": [
            str(item).strip()
            for item in list(payload.get("rule_paths") or [])
            if str(item).strip()
        ],
        "rule_count": int(payload.get("rule_count") or 0),
    }
    contract["workspace_digest"] = json_digest(contract)
    return contract


def build_workspace_reference_snapshot(
    cwd: str | Path,
    *,
    extra_skill_roots: Optional[Sequence[str | Path]],
    max_chars: int,
    build_workspace_prompt_context: Callable[..., Any],
    safe_resolve: Callable[[Path], Path],
    text_digest: Callable[[str], str],
    discover_project_doc_paths: Callable[[Path], list[Path]],
    path_signature: Callable[[Path], Dict[str, Any]],
    workspace_trust_level: Callable[[Path], str],
) -> Dict[str, Any]:
    resolved_cwd = safe_resolve(Path(cwd))
    context = build_workspace_prompt_context(
        resolved_cwd,
        extra_skill_roots=extra_skill_roots,
    )
    full_instructions_text = str(getattr(context, "instructions_text", "") or "").strip()
    instructions_digest = text_digest(full_instructions_text)
    instructions_text = full_instructions_text
    truncated = False
    if max_chars > 0 and len(instructions_text) > max_chars:
        instructions_text = instructions_text[:max_chars]
        truncated = True
    docs = [
        path_signature(path)
        for path in discover_project_doc_paths(resolved_cwd)
    ]
    instruction_sources = _normalized_instruction_sources(
        getattr(context, "instruction_sources", None)
    ) or _default_instruction_sources(docs)
    rule_paths = _rule_paths_from_sources(instruction_sources)
    skills = [
        {
            "name": str(getattr(item, "name", "") or "").strip(),
            "description": str(getattr(item, "description", "") or "").strip(),
            "path": str(getattr(item, "path", "")).replace("\\", "/"),
        }
        for item in list(getattr(context, "skills", []) or [])
    ]
    snapshot = {
        "cwd": str(resolved_cwd).replace("\\", "/"),
        "workspace_root": str(resolved_cwd).replace("\\", "/"),
        "trust_level": workspace_trust_level(resolved_cwd),
        "instructions_text": instructions_text,
        "instructions_digest": instructions_digest,
        "instructions_truncated": bool(truncated),
        "docs": docs,
        "skills": skills,
        "instruction_sources": instruction_sources,
        "rule_paths": rule_paths,
        "rule_count": len(rule_paths),
    }
    snapshot["workspace_digest"] = workspace_contract(snapshot).get("workspace_digest") or ""
    return snapshot


def workspace_reference_diff(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
) -> Dict[str, Any]:
    return workspace_context_reference_projection_runtime_helpers.workspace_reference_diff(
        previous,
        current,
        normalize_instruction_sources_fn=_normalized_instruction_sources,
    )


def render_workspace_context_update_message(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    *,
    max_chars: int,
) -> Optional[str]:
    return workspace_context_reference_projection_runtime_helpers.render_workspace_context_update_message(
        previous,
        current,
        max_chars=max_chars,
        workspace_reference_diff_fn=workspace_reference_diff,
    )


def workspace_instructions_excerpt(
    current: Dict[str, Any],
    *,
    max_chars: int,
) -> str:
    return workspace_context_reference_projection_runtime_helpers.workspace_instructions_excerpt(
        current,
        max_chars=max_chars,
    )


def build_workspace_reference_context_item(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    *,
    max_chars: int,
) -> Optional[Dict[str, Any]]:
    return workspace_context_reference_projection_runtime_helpers.build_workspace_reference_context_item(
        previous,
        current,
        max_chars=max_chars,
        workspace_reference_diff_fn=workspace_reference_diff,
        normalize_instruction_sources_fn=_normalized_instruction_sources,
        workspace_instructions_excerpt_fn=lambda payload, limit: workspace_instructions_excerpt(
            payload,
            max_chars=limit,
        ),
    )


def render_workspace_reference_context_item_message(item: Dict[str, Any]) -> Optional[str]:
    return workspace_context_reference_projection_runtime_helpers.render_workspace_reference_context_item_message(item)


def json_digest(payload: Dict[str, Any]) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
