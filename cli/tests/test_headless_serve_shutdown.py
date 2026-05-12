import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from cli.agent_cli import headless_stream_runtime_helpers as helpers
from cli.scripts import run_multiturn_planning_probe as planning_probe
from cli.scripts.run_multiturn_planning_probe_case_helpers import ValidationCommand


def test_run_serve_loop_returns_zero_when_client_stdout_closes() -> None:
    stdin = io.StringIO(json.dumps({"id": "1", "prompt": "hello"}) + "\n")

    def _execute_prompt(*args, **kwargs):
        return {"assistant": "unused"}

    code = helpers.run_serve_loop(
        object(),
        input_stream=stdin,
        output_stream=io.StringIO(),
        emit_json_line_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(BrokenPipeError()),
        request_id_for_payload_fn=lambda payload: (
            str(payload.get("id")) if isinstance(payload, dict) else None
        ),
        resolve_serve_prompt_fn=lambda payload: str(payload["prompt"]),
        execute_prompt_fn=_execute_prompt,
        prompt_response_to_dict_fn=lambda _response: {"assistant_text": "ok"},
        exit_code_for_response_fn=lambda _response: 0,
    )

    assert code == 0


def test_shutdown_serve_process_drains_stdout_tail(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        "sys.stdin.read()\n"
        'sys.stdout.write(\'{"type":"tail"}\\n\')\n'
        "sys.stdout.flush()\n"
    )
    stderr_path = tmp_path / "stderr.txt"
    stdout_tail_path = tmp_path / "stdout.tail.txt"
    stderr_file = stderr_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None
    proc.stdin.write("hello\n")
    proc.stdin.flush()

    shutdown = planning_probe._shutdown_serve_process(
        proc,
        stderr_file=stderr_file,
        stdout_tail_path=stdout_tail_path,
        wait_timeout_s=2,
        terminate_timeout_s=1,
        kill_timeout_s=1,
    )

    assert shutdown["returncode"] == 0
    assert shutdown["terminated"] is False
    assert shutdown["killed"] is False
    assert stdout_tail_path.read_text(encoding="utf-8") == '{"type":"tail"}\n'


def test_case_c_scope_pivot_followup_prompt_requires_pytest_collectable_layout() -> None:
    case = next(spec for spec in planning_probe.CASES if spec.name == "case_c_scope_pivot")

    assert "pytest -q" in case.prompts[2]
    assert "收集并通过" in case.prompts[2]


def test_multiturn_planning_validation_runs_pytest_with_current_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = {}

    def _fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    results = planning_probe._run_validation(
        workspace=tmp_path,
        out_dir=tmp_path / "validation",
        commands=(ValidationCommand(name="pytest", command=("pytest", "-q")),),
    )

    assert captured["command"] == [sys.executable, "-m", "pytest", "-q"]
    assert results[0]["command"] == ["pytest", "-q"]
    assert results[0]["effective_command"] == [sys.executable, "-m", "pytest", "-q"]
