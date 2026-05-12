from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.workspace_context import DEFAULT_PROJECT_DOC_FILENAME, LOCAL_PROJECT_DOC_FILENAME

_PROJECT_SCOPE = "project"
_PROJECT_AND_LOCAL_SCOPE = "project_and_local"
_RULES_KEEP_SINGLE = "keep_single"
_RULES_SUGGEST_ONLY = "suggest_only"
_RULES_GENERATE = "generate"


def project_doc_artifact(scan_summary: dict[str, Any], *, refresh: bool, selection: dict[str, Any]) -> dict[str, Any]:
    target_path = Path(str(scan_summary.get("project_doc_path") or "")).resolve()
    existing_project_text = str(scan_summary.get("existing_project_doc_text") or "")
    legacy_project_text = str(scan_summary.get("legacy_project_doc_text") or "")
    base_source = DEFAULT_PROJECT_DOC_FILENAME
    if existing_project_text:
        base_text = existing_project_text
        base_source = DEFAULT_PROJECT_DOC_FILENAME
    elif legacy_project_text:
        base_text = legacy_project_text
        base_source = str(Path(str(scan_summary.get("legacy_project_doc_path") or "")).name or DEFAULT_PROJECT_DOC_FILENAME)
    else:
        base_text = ""
        base_source = "template"

    if target_path.is_file() and not refresh:
        return {
            "path": str(target_path),
            "kind": "project_doc",
            "change_mode": "noop",
            "content": existing_project_text,
            "base_source": base_source,
        }

    rendered = render_project_doc_draft(scan_summary, base_text=base_text, selection=selection)
    existing_target_text = existing_project_text if target_path.is_file() else ""
    change_mode = change_mode_for_artifact(existing_target_text, rendered, target_exists=target_path.is_file())
    return {
        "path": str(target_path),
        "kind": "project_doc",
        "change_mode": change_mode,
        "content": rendered,
        "base_source": base_source,
    }


def local_doc_artifact(scan_summary: dict[str, Any]) -> dict[str, Any]:
    target_path = Path(str(scan_summary.get("local_doc_path") or "")).resolve()
    existing_text = str(scan_summary.get("existing_local_doc_text") or "")
    if existing_text:
        return {
            "path": str(target_path),
            "kind": "local_doc",
            "change_mode": "noop",
            "content": existing_text,
            "base_source": LOCAL_PROJECT_DOC_FILENAME,
        }
    return {
        "path": str(target_path),
        "kind": "local_doc",
        "change_mode": "create",
        "content": render_local_doc_draft(scan_summary),
        "base_source": "template",
    }


def rules_doc_artifact(scan_summary: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(str(scan_summary.get("project_root") or "")).resolve()
    target_path = project_root / ".agenthub" / "rules" / "agenthub_init_repository_snapshot.md"
    existing_text = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
    rendered = render_rule_doc_draft(scan_summary)
    change_mode = change_mode_for_artifact(existing_text, rendered, target_exists=target_path.is_file())
    if not target_path.is_file() and rendered.strip():
        change_mode = "split_rules"
    return {
        "path": str(target_path),
        "kind": "rules_doc",
        "change_mode": change_mode,
        "content": rendered,
        "base_source": ".agenthub/rules",
    }


def render_project_doc_draft(scan_summary: dict[str, Any], *, base_text: str, selection: dict[str, Any]) -> str:
    current = str(base_text or "").strip()
    if not current:
        project_name = str(scan_summary.get("project_name") or "Project").strip() or "Project"
        current = "\n".join(
            [
                f"# {project_name}",
                "",
                "Stable repository guidance for AgentHub runs.",
                "",
                "## Engineering Expectations",
                "- Keep changes scoped and easy to review.",
                "- Prefer the smallest diff that satisfies the task.",
                "- Run or describe the most relevant validation before handoff.",
                "- Update this file when repo structure or entrypoints change.",
            ]
        )
    current = replace_or_append_managed_section(current, "Repository Snapshot", repository_snapshot_body(scan_summary))
    current = replace_or_append_managed_section(current, "Common Commands", common_commands_body(scan_summary))
    current = replace_or_append_managed_section(current, "Important Paths", important_paths_body(scan_summary))
    if should_render_rules_layout(scan_summary, selection):
        current = replace_or_append_managed_section(current, "Rules Layout", rules_layout_body(scan_summary, selection))
    return current.rstrip() + "\n"


def render_local_doc_draft(scan_summary: dict[str, Any]) -> str:
    project_name = str(scan_summary.get("project_name") or "Project").strip() or "Project"
    return "\n".join(
        [
            f"# {project_name} Local Override",
            "",
            "Keep machine-specific or developer-specific notes here.",
            "",
            "## Private Notes",
            "- Record local credentials, endpoints, and bootstrap steps here.",
            "- Keep secrets and personal workflow details out of `AENGTHUB.md`.",
            "",
            "## Local Commands",
            "- Add local-only helpers here when they should not be committed.",
            "",
        ]
    )


def render_rule_doc_draft(scan_summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "---",
            "description: Managed repository snapshot generated by /init",
            "---",
            "",
            "# Repository Snapshot Rule",
            "",
            "Use this file for stable repo facts that are better isolated from the main `AENGTHUB.md` summary.",
            "",
            repository_snapshot_body(scan_summary),
            "",
            common_commands_body(scan_summary),
            "",
            important_paths_body(scan_summary),
            "",
        ]
    )


def repository_snapshot_body(scan_summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## Repository Snapshot",
            f"- Project root: `{scan_summary.get('project_root') or '-'}`",
            f"- Languages: {_markdown_list(scan_summary.get('languages'))}",
            f"- Frameworks: {_markdown_list(scan_summary.get('frameworks'))}",
            f"- Package managers: {_markdown_list(scan_summary.get('package_managers'))}",
            f"- Existing instruction sources: {_markdown_list(scan_summary.get('ai_instruction_sources'))}",
        ]
    )


def common_commands_body(scan_summary: dict[str, Any]) -> str:
    command_groups = dict(scan_summary.get("command_groups") or {})
    lines = ["## Common Commands"]
    for group_name in ("build", "test", "lint", "format"):
        lines.append(f"- {group_name}: {_markdown_list(command_groups.get(group_name))}")
    return "\n".join(lines)


def important_paths_body(scan_summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## Important Paths",
            f"- README: {_markdown_list(scan_summary.get('readme_paths'))}",
            f"- Manifests: {_markdown_list(scan_summary.get('manifest_paths'))}",
            f"- CI: {_markdown_list(scan_summary.get('ci_paths'))}",
        ]
    )


def rules_layout_body(scan_summary: dict[str, Any], selection: dict[str, Any]) -> str:
    rule_paths = [str(item).strip() for item in list(scan_summary.get("rule_paths") or []) if str(item).strip()]
    generated_path = ".agenthub/rules/agenthub_init_repository_snapshot.md"
    if str(selection.get("rules_mode") or "") == _RULES_GENERATE and generated_path not in rule_paths:
        rule_paths.append(generated_path)
    lines = ["## Rules Layout"]
    lines.append(f"- Mode: {rules_mode_label(str(selection.get('rules_mode') or _RULES_KEEP_SINGLE))}")
    lines.append("- Rule files: " + (_markdown_list(rule_paths) if rule_paths else "-"))
    if str(selection.get("rules_mode") or "") == _RULES_GENERATE:
        lines.append("- Managed split: repository snapshot and commands are also emitted into a rule file.")
    return "\n".join(lines)


def replace_or_append_managed_section(text: str, title: str, body: str) -> str:
    start_marker = f"<!-- AgentHub Init: {title} -->"
    end_marker = f"<!-- /AgentHub Init: {title} -->"
    block = f"{start_marker}\n{body.strip()}\n{end_marker}"
    source = str(text or "").strip()
    start = source.find(start_marker)
    if start >= 0:
        end = source.find(end_marker, start)
        if end >= 0:
            suffix_start = end + len(end_marker)
            prefix = source[:start].rstrip()
            suffix = source[suffix_start:].lstrip()
            return "\n\n".join(part for part in (prefix, block, suffix) if part)
    return f"{source}\n\n{block}" if source else block


def scope_label(scope: str) -> str:
    if scope == _PROJECT_AND_LOCAL_SCOPE:
        return "Project AENGTHUB.md + local override"
    return "Project AENGTHUB.md"


def rules_mode_label(rules_mode: str) -> str:
    if rules_mode == _RULES_GENERATE:
        return "Generate managed rules file"
    if rules_mode == _RULES_SUGGEST_ONLY:
        return "Suggest rules split only"
    return "Keep single AENGTHUB.md"


def should_render_rules_layout(scan_summary: dict[str, Any], selection: dict[str, Any]) -> bool:
    if list(scan_summary.get("rule_paths") or []):
        return True
    return str(selection.get("rules_mode") or "") == _RULES_GENERATE


def stack_summary(scan_summary: dict[str, Any]) -> str:
    parts = [
        list_or_dash(scan_summary.get("languages")),
        list_or_dash(scan_summary.get("frameworks")),
        list_or_dash(scan_summary.get("package_managers")),
    ]
    compact = [part for part in parts if part != "-"]
    return " | ".join(compact) if compact else "-"


def artifact_relpath(artifact: dict[str, Any], scan_summary: dict[str, Any]) -> str:
    project_root = Path(str(scan_summary.get("project_root") or "")).resolve()
    artifact_path = Path(str(artifact.get("path") or "")).resolve()
    try:
        return artifact_path.relative_to(project_root).as_posix()
    except ValueError:
        return str(artifact_path)


def change_mode_for_artifact(existing_text: str, rendered_text: str, *, target_exists: bool) -> str:
    existing = str(existing_text or "").strip()
    rendered = str(rendered_text or "").strip()
    if not rendered:
        return "noop"
    if not target_exists:
        return "create"
    if existing == rendered:
        return "noop"
    return "update"


def _markdown_list(value: Any) -> str:
    items = [str(item).strip() for item in list(value or []) if str(item).strip()]
    if not items:
        return "-"
    return ", ".join(f"`{item}`" for item in items)


def list_or_dash(value: Any) -> str:
    items = [str(item).strip() for item in list(value or []) if str(item).strip()]
    return ", ".join(items) if items else "-"


def refresh_hint(artifacts: list[dict[str, Any]], selection: dict[str, Any]) -> str:
    if bool(selection.get("refresh")):
        return ""
    for artifact in artifacts:
        if artifact.get("kind") == "project_doc" and artifact.get("change_mode") == "noop":
            return "Hint: `AENGTHUB.md` already exists. Re-run `/init --refresh` to regenerate managed snapshot sections."
    return ""


def truncate_text(text: str, *, limit: int) -> str:
    source = str(text or "").strip()
    if len(source) <= limit:
        return source
    return source[: max(0, limit - 48)].rstrip() + "\n...[preview truncated]..."
