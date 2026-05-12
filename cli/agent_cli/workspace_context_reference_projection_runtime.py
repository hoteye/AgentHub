from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def workspace_reference_diff(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    *,
    normalize_instruction_sources_fn: Callable[[Any], list[Dict[str, Any]]],
) -> Dict[str, Any]:
    previous_item = dict(previous or {})
    current_item = dict(current or {})
    prev_docs = {
        str(item.get("path") or ""): item
        for item in list(previous_item.get("docs") or [])
        if isinstance(item, dict)
    }
    next_docs = {
        str(item.get("path") or ""): item
        for item in list(current_item.get("docs") or [])
        if isinstance(item, dict)
    }
    prev_skills = {
        str(item.get("path") or ""): item
        for item in list(previous_item.get("skills") or [])
        if isinstance(item, dict)
    }
    next_skills = {
        str(item.get("path") or ""): item
        for item in list(current_item.get("skills") or [])
        if isinstance(item, dict)
    }
    prev_instruction_sources = {
        str(item.get("path") or ""): item
        for item in normalize_instruction_sources_fn(previous_item.get("instruction_sources"))
    }
    next_instruction_sources = {
        str(item.get("path") or ""): item
        for item in normalize_instruction_sources_fn(current_item.get("instruction_sources"))
    }
    prev_rule_paths = sorted(
        str(item).strip()
        for item in list(previous_item.get("rule_paths") or [])
        if str(item).strip()
    )
    next_rule_paths = sorted(
        str(item).strip()
        for item in list(current_item.get("rule_paths") or [])
        if str(item).strip()
    )
    docs_added = sorted(path for path in next_docs if path and path not in prev_docs)
    docs_removed = sorted(path for path in prev_docs if path and path not in next_docs)
    docs_updated = sorted(
        path
        for path in next_docs
        if path in prev_docs
        and (
            int(next_docs[path].get("mtime_ns") or 0) != int(prev_docs[path].get("mtime_ns") or 0)
            or int(next_docs[path].get("size") or 0) != int(prev_docs[path].get("size") or 0)
            or str(next_docs[path].get("content_digest") or "").strip()
            != str(prev_docs[path].get("content_digest") or "").strip()
        )
    )
    skills_added = sorted(path for path in next_skills if path and path not in prev_skills)
    skills_removed = sorted(path for path in prev_skills if path and path not in next_skills)
    skills_updated = sorted(
        path
        for path in next_skills
        if path in prev_skills
        and str(next_skills[path].get("description") or "").strip()
        != str(prev_skills[path].get("description") or "").strip()
    )
    instruction_sources_added = sorted(
        path for path in next_instruction_sources if path and path not in prev_instruction_sources
    )
    instruction_sources_removed = sorted(
        path for path in prev_instruction_sources if path and path not in next_instruction_sources
    )
    instruction_sources_updated = sorted(
        path
        for path in next_instruction_sources
        if path in prev_instruction_sources
        and (
            str(next_instruction_sources[path].get("kind") or "").strip()
            != str(prev_instruction_sources[path].get("kind") or "").strip()
            or str(next_instruction_sources[path].get("scope") or "").strip()
            != str(prev_instruction_sources[path].get("scope") or "").strip()
            or int(next_instruction_sources[path].get("order") or 0)
            != int(prev_instruction_sources[path].get("order") or 0)
        )
    )
    rule_paths_added = sorted(path for path in next_rule_paths if path not in prev_rule_paths)
    rule_paths_removed = sorted(path for path in prev_rule_paths if path not in next_rule_paths)
    digest_before = str(previous_item.get("instructions_digest") or "").strip()
    digest_after = str(current_item.get("instructions_digest") or "").strip()
    rule_count_before = int(previous_item.get("rule_count") or len(prev_rule_paths) or 0)
    rule_count_after = int(current_item.get("rule_count") or len(next_rule_paths) or 0)
    return {
        "changed": bool(
            digest_before != digest_after
            or docs_added
            or docs_removed
            or docs_updated
            or skills_added
            or skills_removed
            or skills_updated
            or instruction_sources_added
            or instruction_sources_removed
            or instruction_sources_updated
            or rule_paths_added
            or rule_paths_removed
            or rule_count_before != rule_count_after
            or str(previous_item.get("cwd") or "") != str(current_item.get("cwd") or "")
            or str(previous_item.get("workspace_root") or "") != str(current_item.get("workspace_root") or "")
            or str(previous_item.get("trust_level") or "") != str(current_item.get("trust_level") or "")
        ),
        "is_initial": not bool(previous_item),
        "digest_before": digest_before,
        "digest_after": digest_after,
        "docs_added": docs_added,
        "docs_removed": docs_removed,
        "docs_updated": docs_updated,
        "skills_added": skills_added,
        "skills_removed": skills_removed,
        "skills_updated": skills_updated,
        "instruction_sources_added": instruction_sources_added,
        "instruction_sources_removed": instruction_sources_removed,
        "instruction_sources_updated": instruction_sources_updated,
        "rule_paths_added": rule_paths_added,
        "rule_paths_removed": rule_paths_removed,
        "rule_count_before": rule_count_before,
        "rule_count_after": rule_count_after,
    }


def render_workspace_context_update_message(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    *,
    max_chars: int,
    workspace_reference_diff_fn: Callable[[Optional[Dict[str, Any]], Dict[str, Any]], Dict[str, Any]],
) -> Optional[str]:
    diff = workspace_reference_diff_fn(previous, current)
    if not diff.get("changed"):
        return None
    if diff.get("is_initial"):
        body = str(current.get("instructions_text") or "").strip()
        if max_chars > 0 and len(body) > max_chars:
            body = body[:max_chars]
        lines = [
            "REFERENCE_CONTEXT_BASELINE:",
            f"cwd={current.get('cwd') or '-'}",
            f"workspace_root={current.get('workspace_root') or current.get('cwd') or '-'}",
            f"trust={current.get('trust_level') or '-'}",
            f"instructions_digest={diff.get('digest_after') or '-'}",
            "",
            body or "(no workspace instructions)",
        ]
        return "\n".join(lines).strip()
    lines = [
        "REFERENCE_CONTEXT_UPDATE:",
        f"cwd={current.get('cwd') or '-'}",
        f"workspace_root={current.get('workspace_root') or current.get('cwd') or '-'}",
        f"trust={current.get('trust_level') or '-'}",
        f"digest_before={diff.get('digest_before') or '-'}",
        f"digest_after={diff.get('digest_after') or '-'}",
    ]
    for key in (
        "docs_added",
        "docs_removed",
        "docs_updated",
        "skills_added",
        "skills_removed",
        "skills_updated",
        "instruction_sources_added",
        "instruction_sources_removed",
        "instruction_sources_updated",
        "rule_paths_added",
        "rule_paths_removed",
    ):
        values = list(diff.get(key) or [])
        if values:
            lines.append(f"{key}={','.join(values[:8])}")
    body = str(current.get("instructions_text") or "").strip()
    if body:
        if max_chars > 0 and len(body) > max_chars:
            body = body[:max_chars]
        lines.extend(["", "UPDATED_INSTRUCTIONS_EXCERPT:", body])
    return "\n".join(lines).strip()


def workspace_instructions_excerpt(
    current: Dict[str, Any],
    *,
    max_chars: int,
) -> str:
    body = str(current.get("instructions_text") or "").strip()
    if max_chars > 0 and len(body) > max_chars:
        body = body[:max_chars]
    return body


def build_workspace_reference_context_item(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    *,
    max_chars: int,
    workspace_reference_diff_fn: Callable[[Optional[Dict[str, Any]], Dict[str, Any]], Dict[str, Any]],
    normalize_instruction_sources_fn: Callable[[Any], list[Dict[str, Any]]],
    workspace_instructions_excerpt_fn: Callable[[Dict[str, Any], int], str],
) -> Optional[Dict[str, Any]]:
    diff = workspace_reference_diff_fn(previous, current)
    if not diff.get("changed"):
        return None
    return {
        "item_type": "workspace_context",
        "source": "runtime:workspace_context",
        "label": "workspace_context_baseline" if diff.get("is_initial") else "workspace_context_update",
        "path": str(current.get("cwd") or ""),
        "description": "baseline" if diff.get("is_initial") else "update",
        "metadata": {
            "workspace_root": str(current.get("workspace_root") or current.get("cwd") or ""),
            "trust_level": str(current.get("trust_level") or ""),
            "instructions_digest": str(diff.get("digest_after") or ""),
            "instructions_excerpt": workspace_instructions_excerpt_fn(current, max_chars),
            "is_initial": bool(diff.get("is_initial")),
            "digest_before": str(diff.get("digest_before") or ""),
            "docs": list(current.get("docs") or []),
            "skills": list(current.get("skills") or []),
            "instruction_sources": normalize_instruction_sources_fn(current.get("instruction_sources")),
            "rule_paths": [
                str(item).strip()
                for item in list(current.get("rule_paths") or [])
                if str(item).strip()
            ],
            "rule_count": int(current.get("rule_count") or 0),
            "diff": {
                "docs_added": list(diff.get("docs_added") or []),
                "docs_removed": list(diff.get("docs_removed") or []),
                "docs_updated": list(diff.get("docs_updated") or []),
                "skills_added": list(diff.get("skills_added") or []),
                "skills_removed": list(diff.get("skills_removed") or []),
                "skills_updated": list(diff.get("skills_updated") or []),
                "instruction_sources_added": list(diff.get("instruction_sources_added") or []),
                "instruction_sources_removed": list(diff.get("instruction_sources_removed") or []),
                "instruction_sources_updated": list(diff.get("instruction_sources_updated") or []),
                "rule_paths_added": list(diff.get("rule_paths_added") or []),
                "rule_paths_removed": list(diff.get("rule_paths_removed") or []),
                "rule_count_before": int(diff.get("rule_count_before") or 0),
                "rule_count_after": int(diff.get("rule_count_after") or 0),
            },
        },
    }


def render_workspace_reference_context_item_message(item: Dict[str, Any]) -> Optional[str]:
    payload = dict(item or {})
    if str(payload.get("item_type") or "").strip() != "workspace_context":
        return None
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    is_initial = bool(metadata.get("is_initial")) or str(payload.get("label") or "").strip() == "workspace_context_baseline"
    excerpt = str(metadata.get("instructions_excerpt") or "").strip()
    trust_level = str(metadata.get("trust_level") or "").strip() or "-"
    cwd = str(payload.get("path") or "").strip() or "-"
    digest_after = str(metadata.get("instructions_digest") or "").strip() or "-"
    rule_count = int(metadata.get("rule_count") or 0)
    if is_initial:
        lines = [
            "REFERENCE_CONTEXT_BASELINE:",
            f"cwd={cwd}",
            f"trust={trust_level}",
            f"instructions_digest={digest_after}",
            f"rule_count={rule_count}",
            "",
            excerpt or "(no workspace instructions)",
        ]
        return "\n".join(lines).strip()
    lines = [
        "REFERENCE_CONTEXT_UPDATE:",
        f"cwd={cwd}",
        f"trust={trust_level}",
        f"digest_before={str(metadata.get('digest_before') or '').strip() or '-'}",
        f"digest_after={digest_after}",
        f"rule_count={rule_count}",
    ]
    diff = metadata.get("diff")
    if isinstance(diff, dict):
        for key in (
            "docs_added",
            "docs_removed",
            "docs_updated",
            "skills_added",
            "skills_removed",
            "skills_updated",
            "instruction_sources_added",
            "instruction_sources_removed",
            "instruction_sources_updated",
            "rule_paths_added",
            "rule_paths_removed",
        ):
            values = [str(value).strip() for value in list(diff.get(key) or []) if str(value).strip()]
            if values:
                lines.append(f"{key}={','.join(values[:8])}")
    if excerpt:
        lines.extend(["", "UPDATED_INSTRUCTIONS_EXCERPT:", excerpt])
    return "\n".join(lines).strip()
