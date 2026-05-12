from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

try:
    from cli.scripts.script_runtime_helpers import (
        ensure_script_import_paths,
        resolve_script_provider_run_settings,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import (  # type: ignore[no-redef]
        ensure_script_import_paths,
        resolve_script_provider_run_settings,
    )


_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
REPO_ROOT = _SCRIPT_PATHS.repo_root
LIVE_HARNESS = CLI_ROOT / "scripts" / "approval_continuation_live_harness.py"
DEFAULT_CODEX_REF_ROOT = Path("/home/lyc/project/AgentHubRef/codex_ref")
DEFAULT_CODEX_BIN = DEFAULT_CODEX_REF_ROOT / "codex-rs" / "target" / "debug" / "codex"
DEFAULT_CODEX_APP_SERVER_TEST_CLIENT = (
    DEFAULT_CODEX_REF_ROOT / "codex-rs" / "target" / "debug" / "codex-app-server-test-client"
)
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS = 420

try:
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import _write_json, _write_text
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_codex_ref_ab_model_helpers import _write_json, _write_text  # type: ignore[no-redef]


RunSettingsResolver = Callable[..., Any]


def _is_official_openai_base_url(base_url: str) -> bool:
    try:
        hostname = str(urlparse(base_url).hostname or "").strip().lower()
    except Exception:
        hostname = ""
    return hostname == "api.openai.com"


def _default_codex_provider_id(base_url: str) -> str:
    return "openai" if _is_official_openai_base_url(base_url) else "openai-relay"


def _resolve_run_settings(
    args: argparse.Namespace,
    *,
    resolver: RunSettingsResolver = resolve_script_provider_run_settings,
) -> dict[str, str]:
    settings = resolver(
        cwd=CLI_ROOT,
        provider=str(args.provider or "").strip(),
        model=str(args.model or "").strip(),
        reasoning_effort=str(args.reasoning_effort or "").strip(),
        base_url=str(args.openai_base_url or "").strip(),
        default_base_url=DEFAULT_OPENAI_BASE_URL,
        catalog_cwd=CLI_ROOT,
        interaction_profile="codex_openai",
    )
    return {
        "provider": settings.provider_name,
        "agenthub_model": settings.model_key or settings.model,
        "codex_model": settings.model,
        "reasoning_effort": settings.reasoning_effort,
        "base_url": settings.base_url,
        "config_path": str(settings.config_path),
        "auth_path": str(settings.auth_path),
        "api_key": settings.api_key,
        "source": settings.source,
    }


def _build_codex_home(
    *,
    codex_home: Path,
    api_key: str,
    provider_id: str,
    model: str,
    reasoning_effort: str,
    base_url: str,
    workspace: Path,
) -> tuple[Path, Path]:
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_path = codex_home / "auth.json"
    config_path = codex_home / "config.toml"
    _write_json(
        auth_path,
        {
            "OPENAI_API_KEY": api_key,
            "tokens": None,
            "last_refresh": None,
            "auth_mode": "apikey",
        },
    )
    lines = [
        f'model_provider = "{provider_id}"',
        f'model = "{model}"',
        'preferred_auth_method = "apikey"',
        "disable_response_storage = true",
    ]
    if reasoning_effort:
        lines.append(f'model_reasoning_effort = "{reasoning_effort}"')
    if provider_id == "openai" and _is_official_openai_base_url(base_url):
        lines.append(f'openai_base_url = "{base_url}"')
    else:
        lines.extend(
            [
                "",
                f"[model_providers.{provider_id}]",
                f'name = "{provider_id}"',
                f'base_url = "{base_url}"',
                'env_key = "OPENAI_API_KEY"',
                'wire_api = "responses"',
            ]
        )
    lines.extend(
        [
            "",
            f'[projects."{workspace}"]',
            'trust_level = "trusted"',
        ]
    )
    _write_text(config_path, "\n".join(lines) + "\n")
    return config_path, auth_path
