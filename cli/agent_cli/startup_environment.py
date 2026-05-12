from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Mapping
from typing import Any

from cli.agent_cli.host_platform import HostPlatform, current_host_platform


def _parse_env_output(stdout: Any) -> dict[str, str]:
    if isinstance(stdout, bytes):
        raw = stdout
    else:
        raw = str(stdout or "").encode("utf-8", errors="replace")
    parsed: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        key_text = key.decode("utf-8", errors="replace").strip()
        if not key_text:
            continue
        parsed[key_text] = value.decode("utf-8", errors="replace")
    return parsed


def _merge_path_values(current: str, hydrated: str) -> str:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_value in (hydrated, current):
        for entry in str(raw_value or "").split(os.pathsep):
            value = str(entry or "").strip()
            if not value or value in seen:
                continue
            ordered.append(value)
            seen.add(value)
    return os.pathsep.join(ordered)


def _collect_shell_env(
    *,
    shell_program: str,
    shell_args: list[str],
    base_env: dict[str, str],
    run_fn: Any,
) -> dict[str, str]:
    def _restore_default_stop_signals() -> None:
        for name in ("SIGTSTP", "SIGTTIN", "SIGTTOU"):
            signum = getattr(signal, name, None)
            if signum is None:
                continue
            try:
                signal.signal(signum, signal.SIG_DFL)
            except Exception:
                continue

    kwargs = {
        "check": False,
        "capture_output": True,
        "env": base_env,
        "timeout": 2.0,
    }
    if os.name == "posix":
        kwargs["preexec_fn"] = _restore_default_stop_signals
    try:
        completed = run_fn(
            [shell_program, *shell_args, "env -0"],
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError, ValueError):
        return {}
    returncode = getattr(completed, "returncode", 1)
    if returncode is None or int(returncode) != 0:
        return {}
    return _parse_env_output(getattr(completed, "stdout", b""))


def shell_environment_updates(
    *,
    host_platform: HostPlatform | None = None,
    environ: Mapping[str, str] | None = None,
    run_fn: Any = subprocess.run,
) -> dict[str, str]:
    platform = host_platform or current_host_platform()
    if platform.family != "unix":
        return {}
    shell_program = str(platform.resolve_shell_program(None) or "").strip()
    if not shell_program:
        return {}
    base_env = dict(os.environ if environ is None else environ)
    if not str(base_env.get("HOME") or "").strip():
        return {}
    parsed_login = _collect_shell_env(
        shell_program=shell_program,
        shell_args=["-lc"],
        base_env=base_env,
        run_fn=run_fn,
    )
    parsed_interactive = _collect_shell_env(
        shell_program=shell_program,
        shell_args=["-ic"],
        base_env=base_env,
        run_fn=run_fn,
    )
    updates: dict[str, str] = {}
    path_value = str(base_env.get("PATH") or "")
    for parsed in (parsed_interactive, parsed_login):
        candidate = str(parsed.get("PATH") or "").strip()
        if candidate:
            path_value = _merge_path_values(path_value, candidate)
    if path_value.strip():
        updates["PATH"] = path_value
    shell_value = str(parsed_interactive.get("SHELL") or parsed_login.get("SHELL") or "").strip()
    if shell_value:
        updates["SHELL"] = shell_value
    return updates


def apply_shell_environment_updates(
    *,
    host_platform: HostPlatform | None = None,
    environ: Mapping[str, str] | None = None,
    run_fn: Any = subprocess.run,
) -> dict[str, str]:
    updates = shell_environment_updates(
        host_platform=host_platform,
        environ=environ,
        run_fn=run_fn,
    )
    for key, value in updates.items():
        os.environ[str(key)] = str(value)
    return updates
