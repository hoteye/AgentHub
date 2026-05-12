from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from cli.agent_cli.workspace_context_projection_runtime import build_workspace_prompt_context


@dataclass(frozen=True)
class _Context:
    instructions_text: str = ""
    skills: List[Any] = field(default_factory=list)


def test_build_workspace_prompt_context_normalizes_dict_payload_and_instruction_sources(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    docs_payload = {
        "text": "root\n\nrule",
        "sources": [
            {"path": str(root / ".agenthub" / "rules" / "mobile.md"), "kind": "rule", "scope": "project", "order": 2},
            {"path": str(root / "AENGTHUB.md"), "kind": "doc", "scope": "project", "order": 1},
        ],
    }

    context = build_workspace_prompt_context(
        root,
        safe_resolve=lambda path: Path(path).resolve(),
        read_project_docs_fn=lambda _cwd: docs_payload,
        discover_workspace_skills_fn=lambda _cwd, _extra_skill_roots=None: [],
        render_skills_section_fn=lambda _skills: None,
        context_factory=_Context,
        empty_context_factory=_Context,
        extra_skill_roots=None,
    )

    assert "## Active Workspace" in context.instructions_text
    assert f"Current working directory for local file tools: `{str(root.resolve()).replace(chr(92), '/')}`" in context.instructions_text
    assert context.instructions_text.endswith("root\n\nrule")
    instruction_sources = list(getattr(context, "instruction_sources", []))
    assert [item["path"] for item in instruction_sources] == [
        str((root / "AENGTHUB.md").resolve()).replace("\\", "/"),
        str((root / ".agenthub" / "rules" / "mobile.md").resolve()).replace("\\", "/"),
    ]


def test_build_workspace_prompt_context_keeps_plain_text_path(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    context = build_workspace_prompt_context(
        root,
        safe_resolve=lambda path: Path(path).resolve(),
        read_project_docs_fn=lambda _cwd: "root docs",
        discover_workspace_skills_fn=lambda _cwd, _extra_skill_roots=None: [],
        render_skills_section_fn=lambda _skills: None,
        context_factory=_Context,
        empty_context_factory=_Context,
        extra_skill_roots=None,
    )

    assert "## Active Workspace" in context.instructions_text
    assert context.instructions_text.endswith("root docs")
    assert list(getattr(context, "instruction_sources", [])) == []


def test_build_workspace_prompt_context_injects_empty_workspace_scaffold_rule_without_docs(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    context = build_workspace_prompt_context(
        root,
        safe_resolve=lambda path: Path(path).resolve(),
        read_project_docs_fn=lambda _cwd: None,
        discover_workspace_skills_fn=lambda _cwd, _extra_skill_roots=None: [],
        render_skills_section_fn=lambda _skills: None,
        context_factory=_Context,
        empty_context_factory=_Context,
        extra_skill_roots=None,
    )

    assert "## Active Workspace" in context.instructions_text
    assert "## Workspace Defaults" in context.instructions_text
    assert "treat the current directory as the project root" in context.instructions_text
    assert "Do not create an extra top-level subdirectory" in context.instructions_text
    assert list(getattr(context, "instruction_sources", [])) == []
