from __future__ import annotations

import json

from cli.agent_cli.runtime_exec_policy_rules import (
    RUNTIME_EXEC_POLICY_RULES_FILENAME,
    append_runtime_exec_policy_rule,
    load_runtime_exec_policy_rules,
    match_runtime_exec_policy_rule,
    normalize_exec_policy_rule,
    resolve_runtime_exec_policy_rules_load_paths,
    resolve_runtime_exec_policy_rules_path,
)


def test_resolve_runtime_exec_policy_rules_path_uses_project_root_dot_config(tmp_path) -> None:
    root = tmp_path / "workspace"
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".agent_cli").mkdir()

    resolved = resolve_runtime_exec_policy_rules_path(cwd=nested)

    assert resolved == (root / ".config" / RUNTIME_EXEC_POLICY_RULES_FILENAME).resolve()


def test_normalize_exec_policy_rule_canonicalizes_aliases_and_serialization() -> None:
    rule = normalize_exec_policy_rule(
        {
            "decision": "ASK",
            "match_kind": "token_prefix",
            "command": " /usr/bin/python3 -m pytest cli/tests/test_runtime_exec_policy_rules.py ",
            "justification": " approved after review ",
            "source": " approval ",
            "scope": " workspace ",
            "source_metadata": {
                "approved_by": "worker-b",
                "labels": {"reviewed", "trusted"},
            },
        }
    )

    assert rule.decision == "prompt"
    assert rule.match_kind == "prefix"
    assert rule.command_tokens == (
        "/usr/bin/python3",
        "-m",
        "pytest",
        "cli/tests/test_runtime_exec_policy_rules.py",
    )
    assert rule.normalized_command == "/usr/bin/python3 -m pytest cli/tests/test_runtime_exec_policy_rules.py"
    assert rule.program_name == "/usr/bin/python3"
    assert rule.program_basename == "python3"
    assert rule.justification == "approved after review"
    assert rule.source == "approval"
    assert rule.scope == "workspace"

    payload = rule.to_dict()

    assert payload["rule_id"] == "workspace:prefix:/usr/bin/python3 -m pytest cli/tests/test_runtime_exec_policy_rules.py"
    assert payload["source_metadata"] == {
        "approved_by": "worker-b",
        "labels": ["reviewed", "trusted"],
    }


def test_append_runtime_exec_policy_rule_is_append_only_and_load_merges_latest_entry(tmp_path) -> None:
    path = tmp_path / ".config" / RUNTIME_EXEC_POLICY_RULES_FILENAME

    append_runtime_exec_policy_rule(
        {
            "decision": "allow",
            "match_kind": "exact",
            "command": "/bin/ls -la",
            "justification": "initial approval",
            "source": "manual",
        },
        path=path,
    )
    updated = append_runtime_exec_policy_rule(
        {
            "decision": "prompt",
            "match_kind": "exact",
            "command_tokens": ["/bin/ls", "-la"],
            "justification": "re-reviewed",
            "source": "approval",
            "source_metadata": {"ticket": "appr-123"},
        },
        path=path,
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    loaded = load_runtime_exec_policy_rules(path=path)

    assert len(rows) == 2
    assert rows[0]["decision"] == "allow"
    assert rows[1]["decision"] == "prompt"
    assert len(loaded) == 1
    assert loaded[0].identity == updated.identity
    assert loaded[0].decision == "prompt"
    assert loaded[0].justification == "re-reviewed"
    assert loaded[0].source == "approval"
    assert loaded[0].source_metadata == {"ticket": "appr-123"}


def test_load_runtime_exec_policy_rules_merges_legacy_and_preferred_paths(tmp_path) -> None:
    root = tmp_path / "workspace"
    nested = root / "app" / "pkg"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()

    legacy_path = root / ".agent_cli" / RUNTIME_EXEC_POLICY_RULES_FILENAME
    preferred_path = root / ".config" / RUNTIME_EXEC_POLICY_RULES_FILENAME

    append_runtime_exec_policy_rule(
        {
            "decision": "allow",
            "match_kind": "prefix",
            "command": "cat README.md",
            "source": "legacy",
        },
        path=legacy_path,
    )
    append_runtime_exec_policy_rule(
        {
            "decision": "allow",
            "match_kind": "prefix",
            "command": "rg TODO",
            "justification": "legacy rule",
            "source": "legacy",
        },
        path=legacy_path,
    )
    append_runtime_exec_policy_rule(
        {
            "decision": "forbidden",
            "match_kind": "prefix",
            "command_tokens": ["rg", "TODO"],
            "justification": "preferred override",
            "source": "project",
        },
        path=preferred_path,
    )

    load_paths = resolve_runtime_exec_policy_rules_load_paths(cwd=nested)
    loaded = load_runtime_exec_policy_rules(cwd=nested)
    by_command = {rule.normalized_command: rule for rule in loaded}

    assert load_paths == [legacy_path.resolve(), preferred_path.resolve()]
    assert set(by_command) == {"cat README.md", "rg TODO"}
    assert by_command["cat README.md"].decision == "allow"
    assert by_command["rg TODO"].decision == "forbidden"
    assert by_command["rg TODO"].justification == "preferred override"
    assert by_command["rg TODO"].source == "project"


def test_match_runtime_exec_policy_rule_prefers_exact_over_prefix() -> None:
    rules = [
        normalize_exec_policy_rule(
            {
                "decision": "prompt",
                "match_kind": "prefix",
                "command_tokens": ["echo"],
            }
        ),
        normalize_exec_policy_rule(
            {
                "decision": "allow",
                "match_kind": "exact",
                "command": "echo hello",
            }
        ),
    ]

    matched = match_runtime_exec_policy_rule("echo hello", rules=rules)

    assert matched is not None
    assert matched.match_kind == "exact"
    assert matched.decision == "allow"
