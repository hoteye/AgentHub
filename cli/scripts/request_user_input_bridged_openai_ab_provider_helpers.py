from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path


def _agenthub_config(base_url: str, model: str, effort: str) -> str:
    return textwrap.dedent(
        f"""
        model_provider = "openai"
        model = "{model}"
        model_reasoning_effort = "{effort}"
        disable_response_storage = true
        preferred_auth_method = "apikey"
        approvals_reviewer = "user"

        [features.provider_discovery]
        strict_isolation = true

        [model_providers.openai]
        name = "openai"
        base_url = "{base_url}"
        wire_api = "responses"
        default_model = "gpt_54"
        default_mode_request_user_input = true

        [models.gpt_54]
        provider = "openai"
        model_id = "{model}"
        display_name = "{model}"
        planner_kind = "openai_responses"
        wire_api = "responses"
        supports_tools = true
        supports_reasoning = true
        interaction_profile = "codex_openai"
        """
    ).strip() + "\n"


def _codex_config(base_url: str, model: str, effort: str) -> str:
    return textwrap.dedent(
        f"""
        model_provider = "gac"
        model = "{model}"
        model_reasoning_effort = "{effort}"
        preferred_auth_method = "apikey"

        [features]
        default_mode_request_user_input = true

        [model_providers.gac]
        name = "gac"
        base_url = "{base_url}"
        wire_api = "responses"
        """
    ).strip() + "\n"


def _agenthub_command(repo_root: Path) -> list[str]:
    return [sys.executable, str(repo_root / "cli/app_server.py")]


def _codex_command(codex_bin: Path) -> list[str]:
    return [str(codex_bin), "app-server"]


def _agenthub_env(provider_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["AGENTHUB_PROVIDER_HOME"] = str(provider_home)
    env["AGENTHUB_PROVIDER_STRICT_ISOLATION"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _codex_env(codex_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["PYTHONUNBUFFERED"] = "1"
    return env
