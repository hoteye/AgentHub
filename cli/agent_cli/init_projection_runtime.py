from __future__ import annotations

from typing import Any

from cli.agent_cli.init_projection_helpers import (
    _PROJECT_AND_LOCAL_SCOPE,
    _PROJECT_SCOPE,
    _RULES_GENERATE,
    _RULES_KEEP_SINGLE,
    _RULES_SUGGEST_ONLY,
    artifact_relpath,
    list_or_dash,
    local_doc_artifact,
    project_doc_artifact,
    refresh_hint,
    rules_doc_artifact,
    rules_mode_label,
    scope_label,
    stack_summary,
    truncate_text,
)


def default_init_selection(*, refresh: bool = False) -> dict[str, Any]:
    return {
        "scope": _PROJECT_SCOPE,
        "rules_mode": _RULES_KEEP_SINGLE,
        "refresh": bool(refresh),
    }


def selection_from_answers(scope_answer: str, rules_answer: str, *, refresh: bool = False) -> dict[str, Any]:
    normalized_scope = str(scope_answer or "").strip().lower()
    if "local override" in normalized_scope:
        scope = _PROJECT_AND_LOCAL_SCOPE
    else:
        scope = _PROJECT_SCOPE

    normalized_rules = str(rules_answer or "").strip().lower()
    if "generate" in normalized_rules:
        rules_mode = _RULES_GENERATE
    elif "suggest" in normalized_rules:
        rules_mode = _RULES_SUGGEST_ONLY
    else:
        rules_mode = _RULES_KEEP_SINGLE
    return {
        "scope": scope,
        "rules_mode": rules_mode,
        "refresh": bool(refresh),
    }


def build_init_proposal(scan_summary: dict[str, Any], *, selection: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_selection = dict(selection or default_init_selection())
    scope = str(normalized_selection.get("scope") or _PROJECT_SCOPE).strip() or _PROJECT_SCOPE
    rules_mode = str(normalized_selection.get("rules_mode") or _RULES_KEEP_SINGLE).strip() or _RULES_KEEP_SINGLE
    refresh = bool(normalized_selection.get("refresh"))
    artifacts: list[dict[str, Any]] = []

    artifacts.append(project_doc_artifact(scan_summary, refresh=refresh, selection=normalized_selection))
    if scope == _PROJECT_AND_LOCAL_SCOPE:
        artifacts.append(local_doc_artifact(scan_summary))
    if rules_mode == _RULES_GENERATE:
        artifacts.append(rules_doc_artifact(scan_summary))

    summary_text = render_init_preview_summary(scan_summary, selection=normalized_selection, artifacts=artifacts)
    full_text = render_init_preview_full(scan_summary, selection=normalized_selection, artifacts=artifacts)
    return {
        "project_root": str(scan_summary.get("project_root") or ""),
        "project_name": str(scan_summary.get("project_name") or ""),
        "selection": normalized_selection,
        "artifacts": artifacts,
        "summary_text": summary_text,
        "full_text": full_text,
    }


def render_init_preview_summary(
    scan_summary: dict[str, Any],
    *,
    selection: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> str:
    lines = ["Init preview"]
    lines.append(f"Project root: {scan_summary.get('project_root') or '-'}")
    lines.append(f"Scope: {scope_label(str(selection.get('scope') or _PROJECT_SCOPE))}")
    lines.append(f"Rules: {rules_mode_label(str(selection.get('rules_mode') or _RULES_KEEP_SINGLE))}")
    lines.append(f"Refresh: {'true' if bool(selection.get('refresh')) else 'false'}")
    lines.append("Detected stack: " + stack_summary(scan_summary))
    lines.append(f"Existing rule files: {list_or_dash(scan_summary.get('rule_paths'))}")
    lines.append("Existing instruction sources: " + list_or_dash(scan_summary.get("ai_instruction_sources")))
    if str(selection.get("rules_mode") or "") == _RULES_SUGGEST_ONLY:
        lines.append("Suggestion only: this run will not write `.agenthub/rules/` files.")
    lines.append("Planned artifacts:")
    for artifact in artifacts:
        lines.append(
            f"- {artifact.get('change_mode') or '-'} | {artifact_relpath(artifact, scan_summary)} | {artifact.get('kind') or '-'}"
        )
    refresh_hint_text = refresh_hint(artifacts, selection)
    if refresh_hint_text:
        lines.append(refresh_hint_text)
    lines.append("")
    lines.append("Choose the next action.")
    return "\n".join(lines)


def render_init_preview_full(
    scan_summary: dict[str, Any],
    *,
    selection: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> str:
    lines = ["Init preview (full)"]
    lines.append(f"Project root: {scan_summary.get('project_root') or '-'}")
    lines.append(f"Scope: {scope_label(str(selection.get('scope') or _PROJECT_SCOPE))}")
    lines.append(f"Rules: {rules_mode_label(str(selection.get('rules_mode') or _RULES_KEEP_SINGLE))}")
    lines.append(f"Refresh: {'true' if bool(selection.get('refresh')) else 'false'}")
    lines.append("Languages: " + list_or_dash(scan_summary.get("languages")))
    lines.append("Frameworks: " + list_or_dash(scan_summary.get("frameworks")))
    lines.append("Package managers: " + list_or_dash(scan_summary.get("package_managers")))
    command_groups = dict(scan_summary.get("command_groups") or {})
    for group_name in ("build", "test", "lint", "format"):
        lines.append(f"{group_name.title()} commands: " + list_or_dash(command_groups.get(group_name)))
    lines.append("README files: " + list_or_dash(scan_summary.get("readme_paths")))
    lines.append("Manifest files: " + list_or_dash(scan_summary.get("manifest_paths")))
    lines.append("CI files: " + list_or_dash(scan_summary.get("ci_paths")))
    lines.append("Rule files: " + list_or_dash(scan_summary.get("rule_paths")))
    lines.append("Instruction sources: " + list_or_dash(scan_summary.get("ai_instruction_sources")))
    if str(selection.get("rules_mode") or "") == _RULES_SUGGEST_ONLY:
        lines.append("Suggestion only: no rule files are written in this run.")
    refresh_hint_text = refresh_hint(artifacts, selection)
    if refresh_hint_text:
        lines.append(refresh_hint_text)
    for artifact in artifacts:
        lines.append("")
        lines.append(
            f"### {artifact_relpath(artifact, scan_summary)} | {artifact.get('change_mode') or '-'} | {artifact.get('kind') or '-'}"
        )
        content = str(artifact.get("content") or "").strip()
        lines.append(truncate_text(content, limit=1800) if content else "(no content changes)")
    lines.append("")
    lines.append("Choose the next action.")
    return "\n".join(lines)
