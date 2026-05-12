from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "approval_continuation_codex_ref_ab.py"
SPEC = importlib.util.spec_from_file_location("approval_continuation_codex_ref_ab", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_default_codex_provider_id_uses_relay_for_non_official_base_url() -> None:
    assert MODULE._default_codex_provider_id("https://api.openai.com/v1") == "openai"
    assert MODULE._default_codex_provider_id("https://relay.example/v1") == "openai-relay"
    assert MODULE._default_codex_provider_id("https://gaccode.com/codex/v1") == "openai-relay"


def test_prompt_for_cases_uses_expected_side_effects() -> None:
    by_name = {case.name: case for case in MODULE.CASES}
    shell_case = by_name["approve_exec_command"]
    patch_case = by_name["approve_apply_patch"]
    reject_shell_case = by_name["reject_exec_command"]
    reject_patch_case = by_name["reject_apply_patch"]

    shell_prompt = MODULE._prompt_for_case(shell_case)
    patch_prompt = MODULE._prompt_for_case(patch_case)
    reject_shell_prompt = MODULE._prompt_for_case(reject_shell_case)
    reject_patch_prompt = MODULE._prompt_for_case(reject_patch_case)

    assert "printf 'approval-approved\\n' > approval_live_approve.txt" in shell_prompt
    assert "*** Add File: approval_patch_approve.txt" in patch_prompt
    assert "+approval-patch-approved" in patch_prompt
    assert "printf 'approval-rejected\\n' > approval_live_reject.txt" in reject_shell_prompt
    assert "*** Add File: approval_patch_reject.txt" in reject_patch_prompt
    assert "+approval-patch-rejected" in reject_patch_prompt


def test_build_codex_home_writes_ephemeral_config_and_auth(tmp_path: Path) -> None:
    config_path, auth_path = MODULE._build_codex_home(
        codex_home=tmp_path / "codex_home",
        api_key="sk-test",
        provider_id="openai-relay",
        model="gpt-5.5",
        reasoning_effort="xhigh",
        base_url="https://relay.example/v1",
        workspace=tmp_path / "workspace",
    )

    config_text = config_path.read_text(encoding="utf-8")
    auth_payload = json.loads(auth_path.read_text(encoding="utf-8"))

    assert 'model_provider = "openai-relay"' in config_text
    assert 'model = "gpt-5.5"' in config_text
    assert 'model_reasoning_effort = "xhigh"' in config_text
    assert "[model_providers.openai-relay]" in config_text
    assert 'env_key = "OPENAI_API_KEY"' in config_text
    assert auth_payload["OPENAI_API_KEY"] == "sk-test"
    assert auth_payload["auth_mode"] == "apikey"


def test_parse_codex_stdout_detects_approval_and_completed_turn(tmp_path: Path) -> None:
    stdout_path = tmp_path / "codex.stdout.log"
    stdout_path.write_text(
        "\n".join(
            [
                "< commandExecution approval requested for thread t, turn u, item i, approval a",
                "< available decisions: [Accept, Decline, Cancel]",
                "< commandExecution decision for approval #1 on item i: Accept",
                "< item completed: ThreadItem::CommandExecution { status: Completed }",
                "< turn/completed notification: Completed",
            ]
        ),
        encoding="utf-8",
    )

    parsed = MODULE._parse_codex_stdout(stdout_path)

    assert parsed["approval_markers"]["command"] is True
    assert parsed["decision_markers"]["command_accept"] is True
    assert parsed["decision_markers"]["command_decline"] is False
    assert parsed["completed_turn"] is True
    assert parsed["command_completed"] is True


def test_case_verdict_requires_both_side_effects(tmp_path: Path) -> None:
    case = {case.name: case for case in MODULE.CASES}["approve_exec_command"]
    agent_file = {"exists": True, "content": case.expected_content}
    codex_file = {"exists": True, "content": case.expected_content}
    codex_summary = {
        "approval_markers": {"command": True},
        "decision_markers": {"command_accept": True},
        "completed_turn": True,
    }

    verdict, reasons = MODULE._case_verdict(
        case=case,
        agenthub_case={"verdict": "pass"},
        codex_summary=codex_summary,
        agenthub_file=agent_file,
        codex_file=codex_file,
    )

    assert verdict == "pass"
    assert reasons == []


def test_reject_case_verdict_requires_decline_and_absent_files() -> None:
    case = {case.name: case for case in MODULE.CASES}["reject_apply_patch"]
    missing_file = {"exists": False, "content": ""}
    codex_summary = {
        "approval_markers": {"file_change": True},
        "decision_markers": {"file_change_decline": True},
        "completed_turn": True,
    }

    verdict, reasons = MODULE._case_verdict(
        case=case,
        agenthub_case={"verdict": "pass"},
        codex_summary=codex_summary,
        agenthub_file=missing_file,
        codex_file=missing_file,
    )

    assert verdict == "pass"
    assert reasons == []


def test_reject_case_verdict_fails_when_rejected_file_exists() -> None:
    case = {case.name: case for case in MODULE.CASES}["reject_exec_command"]
    codex_summary = {
        "approval_markers": {"command": True},
        "decision_markers": {"command_decline": True},
        "completed_turn": True,
    }

    verdict, reasons = MODULE._case_verdict(
        case=case,
        agenthub_case={"verdict": "pass"},
        codex_summary=codex_summary,
        agenthub_file={"exists": False, "content": ""},
        codex_file={"exists": True, "content": case.expected_content},
    )

    assert verdict == "fail"
    assert reasons == ["codex_rejected_file_should_not_exist"]


def test_main_dry_run_writes_report_without_live_calls(monkeypatch, tmp_path: Path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({"OPENAI_API_KEY": "sk-test"}), encoding="utf-8")
    monkeypatch.setattr(
        MODULE,
        "resolve_script_provider_run_settings",
        lambda **_kwargs: SimpleNamespace(
            provider_name="openai",
            model_key="gpt_55",
            model="gpt-5.5",
            reasoning_effort="xhigh",
            base_url="https://relay.example/v1",
            config_path=str(tmp_path / "config.toml"),
            auth_path=str(auth_path),
            api_key="",
            source="project_local",
        ),
    )

    exit_code = MODULE.main(["--out-root", str(tmp_path / "out"), "--case", "approve_exec_command"])

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["dry_run"] is True
    assert report["verdict"] == "dry_run"
    assert report["agenthub_model"] == "gpt_55"
    assert report["codex_model"] == "gpt-5.5"
    assert report["codex_provider_id"] == "openai-relay"
    assert report["auth"]["path"] == str(auth_path)
    assert report["auth"]["api_key_present"] is False
    assert report["settings"]["source"] == "project_local"
    assert report["results"][0]["case"] == "approve_exec_command"
    assert (tmp_path / "out" / "summary.md").exists()


def test_resolve_run_settings_uses_unified_provider_settings(monkeypatch, tmp_path: Path) -> None:
    received = {}

    def _fake_resolve(**kwargs):
        received.update(kwargs)
        return SimpleNamespace(
            provider_name="openai",
            model_key="gpt_55",
            model="gpt-5.5",
            reasoning_effort="xhigh",
            base_url="https://gaccode.com/codex/v1",
            config_path=tmp_path / "selected-config.toml",
            auth_path=tmp_path / "selected-auth.json",
            api_key="sk-selected",
            source="project_local",
        )

    monkeypatch.setattr(MODULE, "resolve_script_provider_run_settings", _fake_resolve)

    settings = MODULE._resolve_run_settings(
        SimpleNamespace(
            provider="",
            model="",
            reasoning_effort="",
            openai_base_url="",
        )
    )

    assert received["cwd"] == MODULE.CLI_ROOT
    assert received["catalog_cwd"] == MODULE.CLI_ROOT
    assert received["interaction_profile"] == "codex_openai"
    assert settings["provider"] == "openai"
    assert settings["agenthub_model"] == "gpt_55"
    assert settings["codex_model"] == "gpt-5.5"
    assert settings["auth_path"] == str(tmp_path / "selected-auth.json")
    assert settings["api_key"] == "sk-selected"
