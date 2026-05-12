from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from cli.agent_cli.workspace_context_reference_runtime import (
    build_workspace_reference_context_item,
    build_workspace_reference_snapshot,
    workspace_reference_diff,
)


@dataclass
class _FakeContext:
    instructions_text: str = ""
    skills: List[Any] = field(default_factory=list)
    instruction_sources: List[Dict[str, Any]] = field(default_factory=list)


def _safe_resolve(path: Path) -> Path:
    return path.resolve()


def _path_signature(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()).replace("\\", "/"),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def test_workspace_reference_snapshot_exposes_instruction_sources_and_rules(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    docs = [
        root / "AENGTHUB.md",
        root / ".agenthub" / "rules" / "mobile.md",
    ]
    docs[1].parent.mkdir(parents=True)
    docs[0].write_text("project", encoding="utf-8")
    docs[1].write_text("rule", encoding="utf-8")
    instruction_sources = [
        {"path": str(docs[1]), "kind": "rule", "scope": "project", "order": 2},
        {"path": str(docs[0]), "kind": "doc", "scope": "project", "order": 1},
    ]

    snapshot = build_workspace_reference_snapshot(
        root,
        extra_skill_roots=None,
        max_chars=4096,
        build_workspace_prompt_context=lambda *_args, **_kwargs: _FakeContext(
            instructions_text="project\n\nrule",
            skills=[],
            instruction_sources=instruction_sources,
        ),
        safe_resolve=_safe_resolve,
        text_digest=lambda text: "digest-" + str(len(text)),
        discover_project_doc_paths=lambda _cwd: docs,
        path_signature=_path_signature,
        workspace_trust_level=lambda _cwd: "trusted",
    )

    assert [item["path"] for item in snapshot["instruction_sources"]] == [
        str(docs[0].resolve()).replace("\\", "/"),
        str(docs[1].resolve()).replace("\\", "/"),
    ]
    assert snapshot["rule_paths"] == [str(docs[1].resolve()).replace("\\", "/")]
    assert snapshot["rule_count"] == 1


def test_workspace_reference_diff_and_item_include_instruction_source_changes() -> None:
    previous = {
        "cwd": "/repo",
        "trust_level": "trusted",
        "instructions_digest": "a",
        "docs": [],
        "skills": [],
        "instruction_sources": [{"path": "/repo/AENGTHUB.md", "kind": "doc", "scope": "project", "order": 1}],
        "rule_paths": [],
        "rule_count": 0,
    }
    current = {
        "cwd": "/repo",
        "trust_level": "trusted",
        "instructions_digest": "b",
        "docs": [],
        "skills": [],
        "instruction_sources": [
            {"path": "/repo/AENGTHUB.md", "kind": "doc", "scope": "project", "order": 1},
            {"path": "/repo/.agenthub/rules/mobile.md", "kind": "rule", "scope": "project", "order": 2},
        ],
        "rule_paths": ["/repo/.agenthub/rules/mobile.md"],
        "rule_count": 1,
    }

    diff = workspace_reference_diff(previous, current)
    assert diff["changed"] is True
    assert diff["instruction_sources_added"] == ["/repo/.agenthub/rules/mobile.md"]
    assert diff["rule_paths_added"] == ["/repo/.agenthub/rules/mobile.md"]
    assert diff["rule_count_before"] == 0
    assert diff["rule_count_after"] == 1

    item = build_workspace_reference_context_item(previous, current, max_chars=1024)
    assert item is not None
    metadata = dict(item["metadata"])
    assert metadata["rule_count"] == 1
    assert metadata["rule_paths"] == ["/repo/.agenthub/rules/mobile.md"]
    assert metadata["diff"]["instruction_sources_added"] == ["/repo/.agenthub/rules/mobile.md"]

