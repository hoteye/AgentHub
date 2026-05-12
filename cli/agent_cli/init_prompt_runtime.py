from __future__ import annotations

from typing import Any


def build_init_llm_prompt(
    scan_summary: dict[str, Any],
    *,
    refresh: bool,
    auto_confirm: bool,
    interactive_available: bool,
) -> str:
    if refresh:
        return _build_refresh_prompt(
            scan_summary,
            auto_confirm=auto_confirm,
            interactive_available=interactive_available,
        )
    return _build_create_prompt(
        scan_summary,
        auto_confirm=auto_confirm,
        interactive_available=interactive_available,
    )


def _build_create_prompt(
    scan_summary: dict[str, Any],
    *,
    auto_confirm: bool,
    interactive_available: bool,
) -> str:
    command_groups = dict(scan_summary.get("command_groups") or {})
    lines: list[str] = [
        "You are executing AgentHub `/init` for this repository.",
        "",
        "Generate a file named AENGTHUB.md that serves as an AgentHub contributor guide for this repository.",
        "Your goal is to produce a clear, concise, repository-specific Markdown document with descriptive headings and actionable guidance.",
        "",
        "Document requirements:",
        '- Title the document "AgentHub Repository Guidelines".',
        "- Keep it concise. 200-400 words is optimal.",
        "- Include only facts that are useful for future coding agents working in this repository.",
        "- Prefer concrete commands, important paths, architecture boundaries, and project-specific workflow notes.",
        "- Do not include generic engineering advice or exhaustive file listings.",
        "- Do not create skills, hooks, `.agenthub/rules/`, local override files, or settings files.",
        "- Do not call `request_user_input`.",
        "",
        "Recommended sections:",
        "- Project Structure & Module Organization",
        "- Build, Test, and Development Commands",
        "- Coding Style & Naming Conventions",
        "- Testing Guidelines",
        "- Architecture or Runtime Notes, only if relevant",
        "",
        "Repository hints from a deterministic scan:",
        f"- project_root: {scan_summary.get('project_root') or '-'}",
        f"- project_name: {scan_summary.get('project_name') or '-'}",
        f"- languages: {_fmt_list(scan_summary.get('languages'))}",
        f"- frameworks: {_fmt_list(scan_summary.get('frameworks'))}",
        f"- package_managers: {_fmt_list(scan_summary.get('package_managers'))}",
        f"- manifests: {_fmt_list(scan_summary.get('manifest_paths'))}",
        f"- readmes: {_fmt_list(scan_summary.get('readme_paths'))}",
        f"- build_commands: {_fmt_list(command_groups.get('build'))}",
        f"- test_commands: {_fmt_list(command_groups.get('test'))}",
        f"- lint_commands: {_fmt_list(command_groups.get('lint'))}",
        f"- format_commands: {_fmt_list(command_groups.get('format'))}",
        "",
    ]
    if auto_confirm:
        lines.extend(
            [
                "This run was invoked with `/init yes`.",
                "write AENGTHUB.md directly when repository evidence is sufficient.",
            ]
        )
    elif interactive_available:
        lines.extend(
            [
                "Write AENGTHUB.md directly when repository evidence is sufficient. Ask at most one concise question only if the repository facts are genuinely ambiguous.",
            ]
        )
    else:
        lines.extend(
            [
                "Interactive user input is unavailable.",
                "Do not write files. Reply with a compact proposed AENGTHUB.md instead.",
            ]
        )
    return "\n".join(lines).strip()


def _build_refresh_prompt(
    scan_summary: dict[str, Any],
    *,
    auto_confirm: bool,
    interactive_available: bool,
) -> str:
    lines: list[str] = [
        "You are executing AgentHub `/init --refresh` for this repository.",
        "",
        "Goal:",
        "- Refresh the existing `AENGTHUB.md` instruction set for this workspace.",
        "- Keep the result concise and repository-specific.",
        "- Include only information future coding agents are likely to need.",
        "- Prefer build/test/lint commands, architecture constraints, workflow quirks, and important paths.",
        "- Do not include generic engineering advice or obvious file listings.",
        "- Do not create skills, hooks, `.agenthub/rules/`, local override files, or settings files unless the user explicitly asked.",
        "- Do not call `request_user_input`.",
        "",
        "Existing-file safety:",
        "- Treat the current `AENGTHUB.md` conservatively.",
        "- Preserve useful existing guidance and update stale or missing repository facts.",
        "- If repository evidence is insufficient, propose targeted changes instead of guessing.",
        "",
        "Refresh mode:",
        "- Refresh mode is ON.",
        "",
    ]
    if auto_confirm:
        lines.extend(
            [
                "Execution mode:",
                "- This run was invoked with `/init yes`.",
                "- Apply safe, focused updates directly when repository evidence is sufficient.",
                "",
            ]
        )
    elif interactive_available:
        lines.extend(
            [
                "Execution mode:",
                "- Interactive user input is available, but do not ask routine confirmation questions.",
                "- Ask at most one concise question only if repository facts cannot be inferred from files.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Execution mode:",
                "- Interactive user input is unavailable.",
                "- Do not write files; reply with a compact proposed refresh.",
                "",
            ]
        )
    lines.extend(
        [
            "Deterministic repo scan summary:",
            _scan_summary_block(scan_summary),
            "",
            "Recommended workflow:",
            "1. Read only the most relevant repo files needed to verify the scan hints.",
            "2. Update `AENGTHUB.md` when it is safe, or propose targeted changes when it is not.",
            "3. Finish with a short summary of what changed or what is proposed.",
        ]
    )
    return "\n".join(lines).strip()


def _scan_summary_block(scan_summary: dict[str, Any]) -> str:
    command_groups = dict(scan_summary.get("command_groups") or {})
    lines = [
        f"- project_root: {scan_summary.get('project_root') or '-'}",
        f"- project_name: {scan_summary.get('project_name') or '-'}",
        f"- existing_project_doc: {scan_summary.get('existing_project_doc_path') or '-'}",
        f"- legacy_project_doc: {scan_summary.get('legacy_project_doc_path') or '-'}",
        f"- languages: {_fmt_list(scan_summary.get('languages'))}",
        f"- frameworks: {_fmt_list(scan_summary.get('frameworks'))}",
        f"- package_managers: {_fmt_list(scan_summary.get('package_managers'))}",
        f"- readme_paths: {_fmt_list(scan_summary.get('readme_paths'))}",
        f"- manifest_paths: {_fmt_list(scan_summary.get('manifest_paths'))}",
        f"- ci_paths: {_fmt_list(scan_summary.get('ci_paths'))}",
        f"- instruction_sources: {_fmt_list(scan_summary.get('ai_instruction_sources'))}",
        f"- build_commands: {_fmt_list(command_groups.get('build'))}",
        f"- test_commands: {_fmt_list(command_groups.get('test'))}",
        f"- lint_commands: {_fmt_list(command_groups.get('lint'))}",
        f"- format_commands: {_fmt_list(command_groups.get('format'))}",
    ]
    return "\n".join(lines)


def _fmt_list(value: Any) -> str:
    items = [str(item).strip() for item in list(value or []) if str(item).strip()]
    return ", ".join(items) if items else "-"
