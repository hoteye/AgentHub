from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

try:
    from cli.scripts.command_execution_wave03_ab_model_helpers import (
        AgentHubConfigSelection,
        _write_text,
    )
    from cli.scripts.script_runtime_helpers import (
        apply_provider_home_override_env,
        ensure_script_import_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from command_execution_wave03_ab_model_helpers import (  # type: ignore[no-redef]
        AgentHubConfigSelection,
        _write_text,
    )
    from script_runtime_helpers import (  # type: ignore[no-redef]
        apply_provider_home_override_env,
        ensure_script_import_paths,
    )

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
ROOT = _SCRIPT_PATHS.repo_root
CLI_ROOT = _SCRIPT_PATHS.cli_root
DEFAULT_AGENTHUB_MAIN = CLI_ROOT / "agent_cli" / "__main__.py"
DEFAULT_CODEX_REF_ROOT = Path("/home/lyc/project/AgentHubRef/codex_ref")
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _is_official_openai_base_url(base_url: str) -> bool:
    try:
        hostname = str(urlparse(base_url).hostname or "").strip().lower()
    except Exception:
        hostname = ""
    return hostname in {"api.openai.com"}


def _default_codex_provider_id(base_url: str) -> str:
    return "openai" if _is_official_openai_base_url(base_url) else "openai-relay"


def _build_codex_home(
    codex_home: Path,
    api_key: str,
    provider_id: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    _write_text(
        codex_home / "auth.json",
        json.dumps(
            {"OPENAI_API_KEY": api_key, "tokens": None, "last_refresh": None},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    normalized_provider = str(provider_id or "").strip() or "openai"
    lines = [
        f'model_provider = "{normalized_provider}"',
        f'model = "{model}"',
        f'model_reasoning_effort = "{reasoning_effort}"',
        "disable_response_storage = true",
        'approval_policy = "never"',
        'preferred_auth_method = "apikey"',
    ]
    if normalized_provider == "openai" and _is_official_openai_base_url(openai_base_url):
        lines.append(f'openai_base_url = "{openai_base_url}"')
    else:
        lines.extend(
            [
                "",
                f"[model_providers.{normalized_provider}]",
                f'name = "{normalized_provider}"',
                f'base_url = "{openai_base_url}"',
                'wire_api = "responses"',
            ]
        )
    _write_text(codex_home / "config.toml", "\n".join(lines) + "\n")


def _build_agenthub_project_local_config(
    *,
    project_root: Path,
    api_key: str,
    provider_id: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
    interaction_profile: str,
) -> tuple[Path, Path]:
    config_dir = project_root / ".config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    auth_path = config_dir / "auth.json"
    normalized_provider = str(provider_id or "").strip() or _default_codex_provider_id(
        openai_base_url
    )
    api_key_name = "OPENAI_API_KEY"
    lines = [
        f'model_provider = "{normalized_provider}"',
        f'model = "{model}"',
        "",
        f"[model_providers.{normalized_provider}]",
        f'name = "{normalized_provider}"',
        f'base_url = "{openai_base_url}"',
        'wire_api = "responses"',
        f'default_model = "{model}"',
        f'api_key_env = "{api_key_name}"',
        "",
        f'[models."{model}"]',
        f'provider = "{normalized_provider}"',
        f'model_id = "{model}"',
        'planner_kind = "openai_responses"',
        'wire_api = "responses"',
        f'reasoning_effort = "{reasoning_effort}"',
    ]
    normalized_profile = str(interaction_profile or "").strip()
    if normalized_profile:
        lines.append(f'interaction_profile = "{normalized_profile}"')
    _write_text(config_path, "\n".join(lines) + "\n")
    _write_text(auth_path, json.dumps({api_key_name: api_key}, ensure_ascii=False, indent=2) + "\n")
    return config_path, auth_path


def _prepare_agenthub_config(
    *,
    harness_root: Path,
    source_config_path: Path,
    source_auth_path: Path,
    api_key: str,
    config_mode: str,
    provider_id: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
    interaction_profile: str,
) -> AgentHubConfigSelection:
    if config_mode == "project_local":
        project_root = harness_root / "agenthub_project"
        config_path, auth_path = _build_agenthub_project_local_config(
            project_root=project_root,
            api_key=api_key,
            provider_id=provider_id,
            model=model,
            reasoning_effort=reasoning_effort,
            openai_base_url=openai_base_url,
            interaction_profile=interaction_profile,
        )
        return AgentHubConfigSelection(
            config_path=config_path,
            auth_path=auth_path,
            agent_cli_home=None,
            provider_home=config_path.parent,
        )
    agenthub_home = harness_root / "agenthub_home"
    agenthub_home.mkdir(parents=True, exist_ok=True)
    shutil.copy(source_config_path, agenthub_home / "config.toml")
    shutil.copy(source_auth_path, agenthub_home / "auth.json")
    return AgentHubConfigSelection(
        config_path=agenthub_home / "config.toml",
        auth_path=agenthub_home / "auth.json",
        agent_cli_home=agenthub_home,
        provider_home=agenthub_home,
    )


def _prepare_codex_config(
    *,
    harness_root: Path,
    api_key: str,
    config_mode: str,
    provider_id: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
) -> tuple[Path, Path, Path]:
    if config_mode == "ephemeral":
        codex_home = harness_root / "codex_home"
        _build_codex_home(
            codex_home,
            api_key,
            provider_id,
            model,
            reasoning_effort,
            openai_base_url,
        )
        return codex_home / "config.toml", codex_home / "auth.json", codex_home
    codex_home = DEFAULT_CODEX_HOME
    return codex_home / "config.toml", codex_home / "auth.json", codex_home


def _build_agenthub_env(
    *,
    common_env: dict[str, str],
    openai_base_url: str,
    model: str,
    reasoning_effort: str,
    provider_home: Path,
    startup_cwd: Path,
    agent_cli_home: Path | None,
) -> dict[str, str]:
    env = dict(common_env)
    for key in (
        "AGENT_CLI_HOME",
        "AGENTHUB_PROVIDER_HOME",
        "AGENTHUB_STARTUP_CWD",
        "AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE",
        "AGENTHUB_STARTUP_CWD_SOURCE",
    ):
        env.pop(key, None)
    env["OPENAI_BASE_URL"] = openai_base_url
    env["AGENT_CLI_BASE_URL"] = openai_base_url
    env["AGENT_CLI_PROVIDER"] = "openai"
    env["AGENT_CLI_MODEL"] = model
    env["AGENT_CLI_REASONING_EFFORT"] = reasoning_effort
    apply_provider_home_override_env(env, provider_home=provider_home)
    env["AGENTHUB_STARTUP_CWD"] = str(startup_cwd)
    env["AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE"] = "1"
    env["AGENTHUB_STARTUP_CWD_SOURCE"] = "launcher"
    if agent_cli_home is not None:
        env["AGENT_CLI_HOME"] = str(agent_cli_home)
    return env
