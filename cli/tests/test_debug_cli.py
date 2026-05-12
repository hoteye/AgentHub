from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from cli.agent_cli.debug_cli import (
    DEBUG_FILTER_ENV_KEY,
    DEBUG_LOG_DIR_ENV_KEY,
    DEBUG_TEXT_LOG_ENV_KEY,
    START_DEBUG_LOG_ENV_KEY,
    configure_debug_from_args,
    preconfigure_debug_from_argv,
)


def test_preconfigure_debug_from_argv_sets_debug_file_and_sidecar_dir(tmp_path: Path) -> None:
    debug_file = tmp_path / "agenthub.debug.log"
    env: dict[str, str] = {}

    scanned = preconfigure_debug_from_argv(
        ["--debug-file", str(debug_file), "--debug", "api,tool"],
        environ=env,
    )

    assert scanned["enabled"] is True
    assert scanned["debug_filter"] == "api,tool"
    assert scanned["debug_file"] == str(debug_file)
    assert env[DEBUG_TEXT_LOG_ENV_KEY] == str(debug_file)
    assert env[START_DEBUG_LOG_ENV_KEY] == str(debug_file)
    assert env[DEBUG_FILTER_ENV_KEY] == "api,tool"
    assert env[DEBUG_LOG_DIR_ENV_KEY] == f"{debug_file}.d"


def test_configure_debug_from_args_uses_stderr_when_only_debug_flag_present() -> None:
    env: dict[str, str] = {}

    configure_debug_from_args(
        Namespace(debug="api", debug_file=None),
        environ=env,
    )

    assert env[DEBUG_TEXT_LOG_ENV_KEY] == "stderr"
    assert env[START_DEBUG_LOG_ENV_KEY] == "stderr"
    assert env[DEBUG_FILTER_ENV_KEY] == "api"
    assert DEBUG_LOG_DIR_ENV_KEY not in env
