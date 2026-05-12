from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reference_parity_source_must_not_reintroduce_reference_fingerprint_heuristic() -> None:
    source = _read_text(
        REPO_ROOT / "cli" / "agent_cli" / "providers" / "reference_parity.py"
    )

    assert '"/reference/" in fingerprint' not in source
    assert '"reference" in fingerprint' not in source
    assert "'reference' in fingerprint" not in source


def test_interaction_profile_resolution_sources_must_not_use_text_fingerprint_heuristics() -> None:
    candidate_relative_paths = (
        "cli/agent_cli/providers/interaction_profile_config.py",
        "cli/agent_cli/providers/interaction_profile_resolution.py",
        "cli/agent_cli/providers/interaction_contract.py",
        "cli/agent_cli/providers/interaction_profile_loader.py",
    )
    forbidden_regexes = (
        re.compile(r'["\']/(?:reference|codex)/["\']\s+in\s+fingerprint'),
        re.compile(
            r'["\'](?:reference|codex)["\']\s+in\s+(?:provider_name|model|model_key|base_url|fingerprint)'
        ),
    )

    for relative_path in candidate_relative_paths:
        path = REPO_ROOT / relative_path
        if not path.exists():
            continue
        source = _read_text(path)
        for pattern in forbidden_regexes:
            assert pattern.search(source) is None, f"{relative_path} matched {pattern.pattern!r}"


def test_consumers_must_not_use_interaction_profile_without_resolved_contract() -> None:
    consumer_relative_paths = (
        "cli/agent_cli/providers/system_prompts.py",
        "cli/agent_cli/providers/tool_specs.py",
        "cli/agent_cli/providers/responses_tool_specs.py",
    )
    contract_tokens = (
        "resolved_interaction_contract",
        "resolve_interaction_contract",
        "resolved_tool_surface_profile_for_config",
        "resolved_interaction_contract_with_fallback",
    )

    for relative_path in consumer_relative_paths:
        source = _read_text(REPO_ROOT / relative_path)
        if "interaction_profile" not in source:
            continue
        assert any(token in source for token in contract_tokens), (
            f"{relative_path} contains interaction_profile but no resolved contract token"
        )
