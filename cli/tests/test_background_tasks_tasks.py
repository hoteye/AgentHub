from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.agent_cli.background_tasks.models import BackgroundTaskStatus, BackgroundTaskType, TaskEnvelope
from cli.agent_cli.background_tasks.storage import BackgroundTaskStorage
from cli.agent_cli.background_tasks.tasks import (
    BenchmarkRunResult,
    SubprocessRunResult,
    apply_staged_teammate_result,
    execute_background_task,
    reject_staged_teammate_result,
)

def test_execute_background_benchmark_task_records_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_benchmark_ok",
        task_type=BackgroundTaskType.BENCHMARK,
        source="cli",
        payload={"argv": ["--scenario", "single_turn_headless", "--case", "openai:gpt_54"]},
    )
    storage.upsert_envelope(envelope)
    report_path = storage.results_dir / f"{envelope.task_id}_benchmark_report.json"

    def _fake_run(envelope_arg, *, report_path: Path, cwd=None):
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text('{"summary":[{"model":"gpt-5.4"}],"runs":[{"ok":true}]}', encoding="utf-8")
        return BenchmarkRunResult(
            returncode=0,
            command=["python", "benchmark_headless_models.py", "--json"],
            report_path=report_path,
            stdout='{"ok":true}\n',
            stderr="",
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks.run_benchmark_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["report_path"] == str(report_path)
    assert Path(result.artifact["snapshot_path"]).exists()
    assert result.artifact["step_count"] == 1
    assert result.artifact["checkpoint_count"] == 2
    assert result.artifact["current_step_id"] == "step_1"
    assert result.artifact["current_step_status"] == "completed"
    assert "cases=1" in result.summary
    snapshot = json.loads(Path(result.artifact["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["status"] == "completed"
    assert snapshot["step_count"] == 1
    assert snapshot["checkpoint_count"] == 2
    assert snapshot["steps"][0]["status"] == "completed"
    assert snapshot["checkpoints"][-1]["kind"] == "step_completed"
    stored = storage.get_result(envelope.task_id)
    assert stored is not None
    assert stored.status == BackgroundTaskStatus.COMPLETED

def test_execute_background_benchmark_task_records_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_benchmark_fail",
        task_type=BackgroundTaskType.BENCHMARK,
        source="cli",
        payload={"argv": ["--scenario", "single_turn_headless"]},
    )
    storage.upsert_envelope(envelope)
    report_path = storage.results_dir / f"{envelope.task_id}_benchmark_report.json"

    def _fake_run(envelope_arg, *, report_path: Path, cwd=None):
        return BenchmarkRunResult(
            returncode=2,
            command=["python", "benchmark_headless_models.py"],
            report_path=report_path,
            stdout="",
            stderr="AuthenticationError: provider key missing",
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks.run_benchmark_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.FAILED
    assert "AuthenticationError" in result.error
    assert Path(result.artifact["snapshot_path"]).exists()
    assert result.artifact["step_count"] == 1
    assert result.artifact["checkpoint_count"] == 2
    assert result.artifact["current_step_status"] == "failed"
    snapshot = json.loads(Path(result.artifact["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["status"] == "failed"
    assert snapshot["steps"][0]["status"] == "failed"
    assert snapshot["checkpoints"][-1]["kind"] == "step_failed"
    stored = storage.get_result(envelope.task_id)
    assert stored is not None
    assert stored.status == BackgroundTaskStatus.FAILED

def test_execute_background_smoke_task_records_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_smoke_ok",
        task_type=BackgroundTaskType.SMOKE,
        source="cli",
        payload={"kind": "multi_llm", "argv": ["--case", "followup_pwd"]},
    )
    storage.upsert_envelope(envelope)
    report_path = storage.results_dir / f"{envelope.task_id}_smoke_report.json"

    def _fake_run(*args, **kwargs):
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text('{"cases":[{"name":"followup_pwd","ok":true}]}', encoding="utf-8")
        return SubprocessRunResult(
            returncode=0,
            command=["python", "run_multi_llm_live_cases.py", "--out", str(report_path)],
            stdout='{"ok":true}\n',
            stderr="",
            cwd=str(tmp_path),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["kind"] == "multi_llm"
    assert result.artifact["report_path"] == str(report_path)
    assert Path(result.artifact["snapshot_path"]).exists()
    assert result.artifact["current_step_status"] == "completed"
    assert result.artifact["terminal_state"] == "completed"
    assert "smoke completed: multi_llm" in result.summary

def test_execute_background_smoke_task_records_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_smoke_timeout",
        task_type=BackgroundTaskType.SMOKE,
        source="cli",
        payload={"kind": "multi_llm", "argv": ["--case", "followup_pwd"], "timeout_seconds": 12},
    )
    storage.upsert_envelope(envelope)

    def _fake_run(*args, **kwargs):
        return SubprocessRunResult(
            returncode=124,
            command=["python", "run_multi_llm_live_cases.py"],
            stdout="",
            stderr="",
            timed_out=True,
            timeout_seconds=12.0,
            cwd=str(tmp_path),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.FAILED
    assert result.summary == "smoke task timed out: multi_llm"
    assert "timeout_seconds=12" in result.error
    assert result.artifact["timed_out"] is True
    assert result.artifact["timeout_seconds"] == 12.0
    assert result.artifact["terminal_state"] == "timed_out"
    snapshot = json.loads(Path(result.artifact["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["timed_out"] is True
    assert snapshot["timeout_seconds"] == 12.0
    assert snapshot["terminal_state"] == "timed_out"


def test_execute_background_smoke_task_multi_llm_regression_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_smoke_multi_llm_regression",
        task_type=BackgroundTaskType.SMOKE,
        source="cli",
        payload={"kind": "multi_llm_regression"},
    )
    storage.upsert_envelope(envelope)
    seen: dict[str, object] = {}

    def _fake_run(*args, **kwargs):
        seen["command"] = list(kwargs.get("command") or [])
        report_path = storage.results_dir / f"{envelope.task_id}_smoke_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text('{"passed":true}', encoding="utf-8")
        return SubprocessRunResult(
            returncode=0,
            command=list(kwargs.get("command") or []),
            stdout='{"passed":true}\n',
            stderr="",
            cwd=str(tmp_path),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    command = [str(item) for item in list(seen.get("command") or [])]
    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["kind"] == "multi_llm_live_cases"
    assert result.artifact["profile"] == "multi_llm_regression"
    assert result.artifact["script_path"].endswith("run_multi_llm_live_cases.py")
    assert "--profile" in command
    assert "orchestration_smoke" in command
    assert "--strict" in command
    assert "--provider" in command
    assert "openai" in command
    assert "--model" in command
    assert "gpt_54" in command


def test_execute_background_smoke_task_policy_helper_regression_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_smoke_policy_helper_regression",
        task_type=BackgroundTaskType.SMOKE,
        source="cli",
        payload={"preset": "policy_helper_regression", "argv": ["--policy-helper-timeout", "30"]},
    )
    storage.upsert_envelope(envelope)
    seen: dict[str, object] = {}

    def _fake_run(*args, **kwargs):
        seen["command"] = list(kwargs.get("command") or [])
        report_path = storage.results_dir / f"{envelope.task_id}_smoke_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "profile": "policy_helper_regression",
                    "helper_combos": [
                        {"combo_id": "glm_low_latency"},
                        {"combo_id": "deepseek_low_latency"},
                    ],
                    "policy_helper_override": {
                        "provider": "",
                        "model": "",
                        "reasoning_effort": "",
                        "timeout": 0,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return SubprocessRunResult(
            returncode=0,
            command=list(kwargs.get("command") or []),
            stdout='{"passed":true}\n',
            stderr="",
            cwd=str(tmp_path),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    command = [str(item) for item in list(seen.get("command") or [])]
    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["kind"] == "policy_helper_live_cases"
    assert result.artifact["profile"] == "policy_helper_regression"
    assert result.artifact["policy_helper_profile"] == "policy_helper_regression"
    assert result.artifact["policy_helper_helper_combo_ids"] == ["glm_low_latency", "deepseek_low_latency"]
    assert result.artifact["policy_helper_helper_combo_count"] == 2
    assert result.artifact["script_path"].endswith("run_policy_helper_live_cases.py")
    assert "--profile" in command
    assert "policy_helper_regression" in command
    assert "--provider" in command
    assert "--model" in command
    assert "--policy-helper-provider" not in command
    assert "--policy-helper-model" not in command
    assert "profile=policy_helper_regression" in result.summary
    assert "helper_combos=glm_low_latency,deepseek_low_latency" in result.summary
    # user argv should still be appended and preserved
    timeout_values = [
        command[index + 1]
        for index, token in enumerate(command)
        if token == "--policy-helper-timeout" and index + 1 < len(command)
    ]
    assert timeout_values
    assert timeout_values[-1] == "30"

def test_execute_background_teammate_task_records_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_teammate_ok",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={
            "task": "总结当前目录结构",
            "provider": "glm",
            "model": "glm_5",
            "reasoning_effort": "medium",
            "cwd": str(tmp_path),
        },
    )
    storage.upsert_envelope(envelope)

    seen = {}

    def _fake_run(*args, **kwargs):
        seen["command"] = list(kwargs.get("command") or [])
        seen["env"] = dict(kwargs.get("env") or {})
        stdout_lines = [
            json.dumps({"type": "thread.started", "thread_id": "thread_1"}, ensure_ascii=False),
            json.dumps({"type": "turn.started"}, ensure_ascii=False),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "agent_message", "phase": "commentary", "text": "先检查仓库"},
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "command_execution",
                        "command": "pytest -q tests/test_demo.py",
                        "aggregated_output": "1 passed",
                        "exit_code": 0,
                        "status": "completed",
                    },
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_2", "type": "agent_message", "phase": "final_answer", "text": "已完成仓库摘要"},
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}},
                ensure_ascii=False,
            ),
        ]
        stdout_line_callback = kwargs.get("stdout_line_callback")
        if callable(stdout_line_callback):
            for line in stdout_lines:
                stdout_line_callback(line)
        response_sidecar_path = Path(str((kwargs.get("env") or {}).get("AGENT_CLI_HEADLESS_RESPONSE_PATH") or "")).expanduser()
        response_sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        response_sidecar_path.write_text(
            json.dumps(
                {
                    "assistant_text": "已完成仓库摘要",
                    "commentary_text": "先检查仓库",
                    "status": {
                        "provider_name": "openai",
                        "provider_model": "gpt-5.4",
                        "timing_summary": "initial=0.30s | tool_execution=0.10s | total=0.40s",
                        "route_policy_helper": "glm | glm-5 | source=route",
                        "route_tool_followup": "openai | gpt-5.4 | source=main",
                    },
                    "thread_id": "thread_1",
                    "tool_events": [
                        {
                            "name": "apply_patch",
                            "payload": {
                                "changes": [{"path": str(tmp_path / "demo.py"), "change_type": "update"}],
                            },
                        },
                        {
                            "name": "exec_command",
                            "payload": {"command": "pytest -q tests/test_demo.py"},
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return SubprocessRunResult(
            returncode=0,
            command=list(kwargs.get("command") or []),
            stdout="\n".join(stdout_lines) + "\n",
            stderr="",
            cwd=str(tmp_path),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.summary == "已完成仓库摘要"
    assert result.artifact["provider"] == "glm"
    assert result.artifact["model"] == "glm_5"
    assert result.artifact["thread_id"] == "thread_1"
    assert result.artifact["tool_event_names"] == ["apply_patch", "exec_command"]
    assert result.artifact["modified_files"] == ["demo.py"]
    assert result.artifact["commands"] == ["pytest -q tests/test_demo.py"]
    assert result.artifact["test_commands"] == ["pytest -q tests/test_demo.py"]
    assert result.artifact["runtime_provider_name"] == "openai"
    assert result.artifact["runtime_provider_model"] == "gpt-5.4"
    assert result.artifact["runtime_timing_summary"] == "initial=0.30s | tool_execution=0.10s | total=0.40s"
    assert result.artifact["route_report"]["routes"]["policy_helper"] == "glm | glm-5 | source=route"
    assert Path(result.artifact["response_path"]).exists()
    assert Path(result.artifact["snapshot_path"]).exists()
    assert seen["command"][1].endswith("agent_cli/__main__.py")
    assert "--headless" in seen["command"]
    assert "--jsonl" in seen["command"]
    assert "AGENT_CLI_HEADLESS_RESPONSE_PATH" in seen["env"]
    assert seen["env"]["AGENT_CLI_COMMAND_POLICY_MODE"] == "background_teammate"
    assert seen["env"]["AGENT_CLI_TEST_POLICY"] == "scoped_only"
    assert seen["env"]["AGENT_CLI_TEST_LOCK_PATH"].endswith(".agent_cli/locks/test_commands.lock")
    assert result.artifact["stream_event_count"] == 6
    assert result.artifact["commentary_text_preview"] == "先检查仓库"
    snapshot = json.loads(Path(result.artifact["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["modified_files"] == ["demo.py"]
    assert snapshot["commands"] == ["pytest -q tests/test_demo.py"]
    assert snapshot["test_commands"] == ["pytest -q tests/test_demo.py"]
    assert snapshot["route_report"]["provider_name"] == "openai"
    assert snapshot["route_report"]["routes"]["tool_followup"] == "openai | gpt-5.4 | source=main"
    assert snapshot["stream_event_count"] == 6
    assert snapshot["bootstrap_diagnostics"]["cwd_exists"] is True
    assert snapshot["bootstrap_diagnostics"]["is_dir"] is True
    assert result.artifact["terminal_state"] == "completed"
    assert snapshot["terminal_state"] == "completed"

def test_execute_background_teammate_task_records_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_teammate_timeout",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={
            "task": "总结当前目录结构",
            "provider": "glm",
            "model": "glm_5",
            "reasoning_effort": "medium",
            "cwd": str(tmp_path),
            "timeout_seconds": 30,
        },
    )
    storage.upsert_envelope(envelope)

    def _fake_run(*args, **kwargs):
        stdout_lines = [
            json.dumps({"type": "thread.started", "thread_id": "thread_timeout"}, ensure_ascii=False),
            json.dumps({"type": "turn.started"}, ensure_ascii=False),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_0", "type": "agent_message", "phase": "commentary", "text": "先查看仓库结构"},
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "command_execution",
                        "command": "pytest -q tests/test_demo.py",
                        "aggregated_output": "running",
                        "exit_code": None,
                        "status": "running",
                    },
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "mcp_tool_call",
                        "tool": "apply_patch",
                        "arguments": {"patch": "*** Begin Patch\n*** End Patch"},
                        "result": {
                            "structured_content": {
                                "changes": [{"path": str(tmp_path / "demo.py"), "change_type": "update"}],
                            }
                        },
                        "status": "completed",
                    },
                },
                ensure_ascii=False,
            ),
        ]
        stdout_line_callback = kwargs.get("stdout_line_callback")
        if callable(stdout_line_callback):
            for line in stdout_lines:
                stdout_line_callback(line)
        return SubprocessRunResult(
            returncode=124,
            command=list(kwargs.get("command") or []),
            stdout="\n".join(stdout_lines) + "\n",
            stderr="",
            timed_out=True,
            timeout_seconds=30.0,
            cwd=str(tmp_path),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.FAILED
    assert result.summary == "teammate task timed out"
    assert "timeout_seconds=30" in result.error
    assert result.artifact["timed_out"] is True
    assert result.artifact["timeout_seconds"] == 30.0
    assert result.artifact["terminal_state"] == "timed_out"
    assert result.artifact["commands"] == ["pytest -q tests/test_demo.py"]
    assert result.artifact["modified_files"] == ["demo.py"]
    assert result.artifact["commentary_text_preview"] == "先查看仓库结构"
    assert result.artifact["stream_event_count"] == 5
    snapshot = json.loads(Path(result.artifact["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["timed_out"] is True
    assert snapshot["timeout_seconds"] == 30.0
    assert snapshot["terminal_state"] == "timed_out"
    assert snapshot["commands"] == ["pytest -q tests/test_demo.py"]
    assert snapshot["modified_files"] == ["demo.py"]

def test_execute_background_teammate_missing_cwd_records_bootstrap_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    missing_root = tmp_path / "missing_repo"
    envelope = TaskEnvelope(
        task_id="bg_teammate_bootstrap_missing",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={
            "task": "检查仓库状态",
            "provider": "glm",
            "model": "glm_5",
            "cwd": str(missing_root),
        },
    )
    storage.upsert_envelope(envelope)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("subprocess should not run when bootstrap fails")

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fail_if_called)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.FAILED
    assert result.summary == "teammate workspace bootstrap failed"
    assert "workspace root does not exist" in result.error
    diagnostics = result.artifact["bootstrap_diagnostics"]
    assert diagnostics["cwd_exists"] is False
    assert diagnostics["is_dir"] is False
    assert diagnostics["bootstrap_error_category"] == "cwd_missing"
    assert diagnostics["git_root_detected"] is False
    assert diagnostics["dependency_files"] == []
    assert Path(result.artifact["snapshot_path"]).exists()
    assert result.artifact["terminal_state"] == "failed"
    snapshot = json.loads(Path(result.artifact["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["status"] == "failed"
    assert snapshot["terminal_state"] == "failed"
    assert snapshot["bootstrap_diagnostics"]["bootstrap_error_category"] == "cwd_missing"

def test_execute_background_teammate_non_git_repo_records_bootstrap_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live_root = tmp_path / "repo"
    live_root.mkdir(parents=True)
    (live_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_teammate_bootstrap_warning",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={
            "task": "总结当前仓库",
            "provider": "glm",
            "model": "glm_5",
            "cwd": str(live_root),
        },
    )
    storage.upsert_envelope(envelope)

    def _fake_run(*args, **kwargs):
        return SubprocessRunResult(
            returncode=0,
            command=list(kwargs.get("command") or []),
            stdout=json.dumps({"assistant_text": "已完成", "tool_events": []}, ensure_ascii=False),
            stderr="",
            cwd=str(live_root),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["terminal_state"] == "completed"
    diagnostics = result.artifact["bootstrap_diagnostics"]
    assert diagnostics["cwd_exists"] is True
    assert diagnostics["is_dir"] is True
    assert diagnostics["git_root_detected"] is False
    assert diagnostics["bootstrap_error_category"] == ""
    assert diagnostics["dependency_files"] == ["pyproject.toml"]
    assert "git root not detected" in diagnostics["bootstrap_warnings"]

def test_execute_background_teammate_workspace_write_stages_changes_for_final_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live_root = tmp_path / "repo"
    (live_root / "src").mkdir(parents=True)
    (live_root / "src" / "demo.py").write_text("print('old')\n", encoding="utf-8")
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_teammate_stage_ok",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={
            "task": "修复 demo.py",
            "provider": "glm",
            "model": "glm_5",
            "reasoning_effort": "medium",
            "cwd": str(live_root),
            "sandbox_mode": "workspace-write",
            "allowed_paths": ["src"],
        },
    )
    storage.upsert_envelope(envelope)
    seen: dict[str, str] = {}

    def _fake_run(*args, **kwargs):
        stage_cwd = Path(kwargs.get("cwd"))
        seen["cwd"] = str(stage_cwd)
        assert stage_cwd != live_root
        (stage_cwd / "src" / "demo.py").write_text("print('new')\n", encoding="utf-8")
        return SubprocessRunResult(
            returncode=0,
            command=list(kwargs.get("command") or []),
            stdout=json.dumps({"assistant_text": "已修复 demo.py", "tool_events": []}, ensure_ascii=False),
            stderr="",
            cwd=str(stage_cwd),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["staged_workspace"] is True
    assert result.artifact["final_apply_pending"] is True
    assert result.artifact["final_apply_state"] == "pending"
    assert result.artifact["modified_files"] == ["src/demo.py"]
    assert result.artifact["allowed_paths"] == ["src"]
    assert result.artifact["blocked_paths"] == [".git"]
    assert result.artifact["review_commands"] == [
        "/background_task_apply bg_teammate_stage_ok",
        "/background_task_reject bg_teammate_stage_ok",
    ]
    assert Path(result.artifact["review_path"]).exists()
    assert (live_root / "src" / "demo.py").read_text(encoding="utf-8") == "print('old')\n"
    assert Path(seen["cwd"]) == Path(result.artifact["stage_cwd"])
    review = json.loads(Path(result.artifact["review_path"]).read_text(encoding="utf-8"))
    assert review["modified_files"] == ["src/demo.py"]
    assert review["final_apply_state"] == "pending"

    applied = apply_staged_teammate_result(envelope.task_id, storage=storage)

    assert applied is not None
    assert applied.artifact["final_apply_state"] == "applied"
    assert applied.artifact["final_apply_pending"] is False
    assert (live_root / "src" / "demo.py").read_text(encoding="utf-8") == "print('new')\n"


def test_execute_background_teammate_workspace_write_ignores_runtime_artifacts_and_bytecode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live_root = tmp_path / "repo"
    (live_root / "src").mkdir(parents=True)
    (live_root / "src" / "demo.py").write_text("print('old')\n", encoding="utf-8")
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_teammate_stage_ignore_runtime_artifacts",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={
            "task": "修复 demo.py",
            "provider": "glm",
            "model": "glm_5",
            "reasoning_effort": "medium",
            "cwd": str(live_root),
            "sandbox_mode": "workspace-write",
            "allowed_paths": ["src"],
        },
    )
    storage.upsert_envelope(envelope)

    def _fake_run(*args, **kwargs):
        stage_cwd = Path(kwargs.get("cwd"))
        (stage_cwd / "src" / "demo.py").write_text("print('new')\n", encoding="utf-8")
        (stage_cwd / "src" / "__pycache__").mkdir(parents=True, exist_ok=True)
        (stage_cwd / "src" / "__pycache__" / "demo.cpython-313.pyc").write_bytes(b"bytecode")
        (stage_cwd / ".pytest_cache" / "v" / "cache").mkdir(parents=True, exist_ok=True)
        (stage_cwd / ".pytest_cache" / "v" / "cache" / "nodeids").write_text("[]\n", encoding="utf-8")
        (stage_cwd / ".config" / "orchestration").mkdir(parents=True, exist_ok=True)
        (stage_cwd / ".config" / "orchestration" / "run.json").write_text("{}", encoding="utf-8")
        (stage_cwd / "cli" / ".local" / "state" / "huey" / "results").mkdir(parents=True, exist_ok=True)
        (stage_cwd / "cli" / ".local" / "state" / "huey" / "results" / "worker_state.json").write_text("{}", encoding="utf-8")
        (stage_cwd / ".git").mkdir(parents=True, exist_ok=True)
        (stage_cwd / ".git" / "index").write_bytes(b"git-index")
        return SubprocessRunResult(
            returncode=0,
            command=list(kwargs.get("command") or []),
            stdout=json.dumps({"assistant_text": "已修复 demo.py", "tool_events": []}, ensure_ascii=False),
            stderr="",
            cwd=str(stage_cwd),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["final_apply_pending"] is True
    assert result.artifact["final_apply_state"] == "pending"
    assert result.artifact["modified_files"] == ["src/demo.py"]
    assert result.artifact["out_of_scope_files"] == []
    review = json.loads(Path(result.artifact["review_path"]).read_text(encoding="utf-8"))
    assert review["modified_files"] == ["src/demo.py"]
    assert review["out_of_scope_files"] == []


def test_execute_background_teammate_workspace_write_blocks_out_of_scope_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live_root = tmp_path / "repo"
    live_root.mkdir(parents=True)
    storage = BackgroundTaskStorage(results_dir=tmp_path / "results", db_path=tmp_path / "tasks.sqlite3")
    envelope = TaskEnvelope(
        task_id="bg_teammate_stage_blocked",
        task_type=BackgroundTaskType.TEAMMATE,
        source="cli",
        payload={
            "task": "新增 README",
            "provider": "glm",
            "model": "glm_5",
            "reasoning_effort": "medium",
            "cwd": str(live_root),
            "sandbox_mode": "workspace-write",
            "allowed_paths": ["src"],
        },
    )
    storage.upsert_envelope(envelope)

    def _fake_run(*args, **kwargs):
        stage_cwd = Path(kwargs.get("cwd"))
        (stage_cwd / "README.md").write_text("blocked\n", encoding="utf-8")
        return SubprocessRunResult(
            returncode=0,
            command=list(kwargs.get("command") or []),
            stdout=json.dumps({"assistant_text": "已生成 README", "tool_events": []}, ensure_ascii=False),
            stderr="",
            cwd=str(stage_cwd),
        )

    monkeypatch.setattr("cli.agent_cli.background_tasks.tasks._run_logged_subprocess", _fake_run)

    result = execute_background_task(envelope, storage=storage)

    assert result.status == BackgroundTaskStatus.FAILED
    assert result.artifact["final_apply_pending"] is False
    assert result.artifact["final_apply_state"] == "blocked"
    assert result.artifact["out_of_scope_files"] == ["README.md"]
    assert result.artifact["review_commands"] == ["/background_task_reject bg_teammate_stage_blocked"]
    assert not (live_root / "README.md").exists()

    rejected = reject_staged_teammate_result(envelope.task_id, storage=storage)

    assert rejected is not None
    assert rejected.artifact["final_apply_state"] == "rejected"
    assert not (live_root / "README.md").exists()
