from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from cli.scripts.codex_sidecar_phase8_acceptance_checks_runtime import (
    check_fake_approval_roundtrip,
    check_fake_crash_reconnect_resume,
    check_fake_fork_resume,
    check_fake_turn_lifecycle,
    check_real_agenthub_sidecar,
)
from cli.scripts.codex_sidecar_phase8_acceptance_report import CheckResult
from cli.scripts.codex_sidecar_phase8_acceptance_runner import (
    _run_check,
    _run_subprocess_check,
)

CLI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CLI_ROOT.parent
FAKE_CODEX_BIN = CLI_ROOT / "tests" / "fixtures" / "fake_codex_sidecar.py"
PROTOTYPE_PROBE = REPO_ROOT / "prototypes" / "codex_ref_sidecar" / "probe_codex_app_server.py"
TUI_SMOKE_PROBE = CLI_ROOT / "scripts" / "tui_tab_smoke_probe.py"


def run_fake_acceptance(*, cwd: Path, request_timeout: float) -> list[CheckResult]:
    with tempfile.TemporaryDirectory(prefix="agenthub-codex-sidecar-phase8-") as temp_dir:
        state_path = Path(temp_dir) / "fake_sidecar_state.json"
        extra_env = {"FAKE_CODEX_SIDECAR_STATE": str(state_path)}
        return [
            _run_check(
                "fake_sidecar_turn_lifecycle",
                lambda: check_fake_turn_lifecycle(
                    codex_bin=FAKE_CODEX_BIN,
                    cwd=cwd,
                    request_timeout=request_timeout,
                    extra_env=extra_env,
                ),
            ),
            _run_check(
                "fake_sidecar_approval_roundtrip",
                lambda: check_fake_approval_roundtrip(
                    codex_bin=FAKE_CODEX_BIN,
                    cwd=cwd,
                    request_timeout=request_timeout,
                    extra_env=extra_env,
                ),
            ),
            _run_check(
                "fake_sidecar_fork_resume",
                lambda: check_fake_fork_resume(
                    codex_bin=FAKE_CODEX_BIN,
                    cwd=cwd,
                    request_timeout=request_timeout,
                    extra_env=extra_env,
                ),
            ),
            _run_check(
                "fake_sidecar_crash_reconnect_resume",
                lambda: check_fake_crash_reconnect_resume(
                    codex_bin=FAKE_CODEX_BIN,
                    cwd=cwd,
                    request_timeout=request_timeout,
                    extra_env=extra_env,
                ),
            ),
        ]


def run_tui_smoke() -> CheckResult:
    return _run_subprocess_check(
        "tui_tab_smoke_probe",
        [sys.executable, str(TUI_SMOKE_PROBE), "--quiet"],
        timeout=90.0,
        cwd=REPO_ROOT,
    )


def run_real_agenthub_sidecar(
    *,
    codex_bin: Path,
    cwd: Path,
    request_timeout: float,
    turn_timeout: float,
    live_turn: str | None,
    real_fork: bool,
) -> CheckResult:
    return _run_check(
        "real_agenthub_sidecar_adapter",
        lambda: check_real_agenthub_sidecar(
            codex_bin=codex_bin,
            cwd=cwd,
            request_timeout=request_timeout,
            turn_timeout=turn_timeout,
            live_turn=live_turn,
            real_fork=real_fork,
        ),
    )


def run_real_codex_ref_probe(
    *,
    codex_bin: Path,
    cwd: Path,
    request_timeout: float,
    turn_timeout: float,
    live_turn: str | None,
    real_fork: bool,
) -> CheckResult:
    command = [
        sys.executable,
        str(PROTOTYPE_PROBE),
        "--codex-bin",
        str(codex_bin),
        "--cwd",
        str(cwd),
        "--timeout",
        str(request_timeout),
        "--turn-timeout",
        str(turn_timeout),
    ]
    if live_turn:
        command.extend(["--turn", live_turn])
    if real_fork:
        command.append("--fork")
    return _run_subprocess_check(
        "real_codex_ref_native_probe",
        command,
        timeout=max(turn_timeout + request_timeout + 10.0, 30.0),
        cwd=REPO_ROOT,
    )
