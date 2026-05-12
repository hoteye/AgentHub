from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.startup_environment import (
    apply_shell_environment_updates,
    shell_environment_updates,
)


def test_shell_environment_updates_reads_login_shell_path() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args, **kwargs):
        calls.append((list(args), dict(kwargs)))
        if list(args)[1:3] == ["-ic", "env -0"]:
            return SimpleNamespace(
                returncode=0,
                stdout=b"PATH=/interactive/bin:/usr/local/bin\0SHELL=/bin/bash\0",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=b"PATH=/custom/bin:/usr/bin\0SHELL=/bin/zsh\0",
        )

    original_env = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(
            {
                "HOME": "/tmp/home",
                "PATH": "/usr/bin:/bin",
                "SHELL": "/bin/bash",
            }
        )
        updates = shell_environment_updates(host_platform=host, run_fn=fake_run)
    finally:
        os.environ.clear()
        os.environ.update(original_env)

    assert updates == {
        "PATH": "/custom/bin:/usr/bin:/interactive/bin:/usr/local/bin:/bin",
        "SHELL": "/bin/bash",
    }
    assert calls[0][0] == ["/bin/bash", "-lc", "env -0"]
    assert calls[1][0] == ["/bin/bash", "-ic", "env -0"]
    assert calls[0][1]["env"]["HOME"] == "/tmp/home"
    assert calls[1][1]["env"]["HOME"] == "/tmp/home"
    assert calls[0][1]["timeout"] == 2.0
    assert calls[1][1]["timeout"] == 2.0
    if os.name == "posix":
        assert callable(calls[0][1]["preexec_fn"])
        assert callable(calls[1][1]["preexec_fn"])


def test_apply_shell_environment_updates_mutates_process_environment() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")

    def fake_run(args, **kwargs):
        del kwargs
        if list(args)[1:3] == ["-ic", "env -0"]:
            return SimpleNamespace(
                returncode=0,
                stdout=b"PATH=/interactive/bin:/usr/local/bin\0SHELL=/bin/bash\0",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=b"PATH=/hydrated/bin:/usr/bin\0SHELL=/bin/bash\0",
        )

    original_env = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(
            {
                "HOME": "/tmp/home",
                "PATH": "/usr/bin:/bin",
                "SHELL": "/bin/sh",
            }
        )
        updates = apply_shell_environment_updates(host_platform=host, run_fn=fake_run)
        assert updates == {
            "PATH": "/hydrated/bin:/usr/bin:/interactive/bin:/usr/local/bin:/bin",
            "SHELL": "/bin/bash",
        }
        assert os.environ["PATH"] == "/hydrated/bin:/usr/bin:/interactive/bin:/usr/local/bin:/bin"
        assert os.environ["SHELL"] == "/bin/bash"
    finally:
        os.environ.clear()
        os.environ.update(original_env)


def test_shell_environment_updates_treats_timeout_as_empty_update() -> None:
    host = detect_host_platform(system_name="Linux", sys_platform="linux")

    def fake_run(args, **kwargs):
        del args, kwargs
        raise subprocess.TimeoutExpired(cmd=["/bin/bash"], timeout=2.0)

    original_env = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(
            {
                "HOME": "/tmp/home",
                "PATH": "/usr/bin:/bin",
                "SHELL": "/bin/bash",
            }
        )
        updates = shell_environment_updates(host_platform=host, run_fn=fake_run)
    finally:
        os.environ.clear()
        os.environ.update(original_env)

    assert updates == {"PATH": "/usr/bin:/bin"}
