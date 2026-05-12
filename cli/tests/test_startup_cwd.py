from __future__ import annotations

import os

from cli.agent_cli.startup_cwd import (
    STARTUP_CWD_ENV,
    STARTUP_CWD_LAUNCHER_ACTIVE_ENV,
    STARTUP_CWD_SOURCE_ENV,
    STARTUP_CWD_SOURCE_LAUNCHER,
    capture_startup_cwd,
)


def test_capture_startup_cwd_sets_env_from_process_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(STARTUP_CWD_ENV, raising=False)
    monkeypatch.delenv(STARTUP_CWD_LAUNCHER_ACTIVE_ENV, raising=False)
    monkeypatch.delenv(STARTUP_CWD_SOURCE_ENV, raising=False)

    startup_cwd = capture_startup_cwd()

    assert startup_cwd == tmp_path.resolve()
    assert os.environ[STARTUP_CWD_ENV] == str(tmp_path.resolve())


def test_capture_startup_cwd_overwrites_unmarked_existing_env(monkeypatch, tmp_path) -> None:
    configured = tmp_path / "workspace"
    configured.mkdir()
    launch_dir = tmp_path / "launcher"
    launch_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    monkeypatch.setenv(STARTUP_CWD_ENV, str(configured))
    monkeypatch.delenv(STARTUP_CWD_LAUNCHER_ACTIVE_ENV, raising=False)
    monkeypatch.delenv(STARTUP_CWD_SOURCE_ENV, raising=False)

    startup_cwd = capture_startup_cwd()

    assert startup_cwd == launch_dir.resolve()
    assert os.environ[STARTUP_CWD_ENV] == str(launch_dir.resolve())


def test_capture_startup_cwd_preserves_launcher_marked_env(monkeypatch, tmp_path) -> None:
    configured = tmp_path / "workspace"
    configured.mkdir()
    launch_dir = tmp_path / "launcher"
    launch_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    monkeypatch.setenv(STARTUP_CWD_ENV, str(configured))
    monkeypatch.setenv(STARTUP_CWD_LAUNCHER_ACTIVE_ENV, "1")
    monkeypatch.setenv(STARTUP_CWD_SOURCE_ENV, STARTUP_CWD_SOURCE_LAUNCHER)

    startup_cwd = capture_startup_cwd()

    assert startup_cwd == configured.resolve()
    assert os.environ[STARTUP_CWD_ENV] == str(configured)


def test_capture_startup_cwd_rejects_stale_launcher_env(monkeypatch, tmp_path) -> None:
    configured = tmp_path / "workspace"
    configured.mkdir()
    launch_dir = tmp_path / "launcher"
    launch_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    monkeypatch.setenv(STARTUP_CWD_ENV, str(configured))
    monkeypatch.setenv(STARTUP_CWD_SOURCE_ENV, STARTUP_CWD_SOURCE_LAUNCHER)
    monkeypatch.delenv(STARTUP_CWD_LAUNCHER_ACTIVE_ENV, raising=False)

    startup_cwd = capture_startup_cwd()

    assert startup_cwd == launch_dir.resolve()
    assert os.environ[STARTUP_CWD_ENV] == str(launch_dir.resolve())
