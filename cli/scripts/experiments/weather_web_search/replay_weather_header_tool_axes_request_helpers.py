from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path
from typing import Any

from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_model_helpers import DEFAULT_OPENAI_BASE_URL
from cli.scripts.script_runtime_helpers import load_script_provider_management_snapshot


def _default_cli_root() -> Path:
    script_path = Path(__file__).resolve()
    for candidate in script_path.parents:
        if candidate.name == "cli":
            return candidate
    return script_path.parents[3]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _load_agenthub_request(path: Path) -> dict[str, Any]:
    for row in _read_jsonl(path):
        if str(row.get("stage") or "").strip() == "responses.send.request_raw":
            payload = row.get("payload") or {}
            request = payload.get("request")
            if isinstance(request, dict):
                return copy.deepcopy(request)
    raise RuntimeError(f"missing AgentHub request_raw in {path}")


def _load_codex_request(path: Path) -> dict[str, Any]:
    for row in _read_jsonl(path):
        if str(row.get("stage") or "").strip() == "stream_responses_api.request.raw":
            payload = row.get("payload")
            if isinstance(payload, dict):
                return copy.deepcopy(payload)
    raise RuntimeError(f"missing Codex request_raw in {path}")


def _load_proxy_headers(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    rows = _read_jsonl(path)
    if len(rows) < 2:
        raise RuntimeError(f"expected at least 2 proxy rows in {path}")
    agenthub_headers = {str(k): str(v) for k, v in dict(rows[0].get("headers") or {}).items()}
    codex_headers = {str(k): str(v) for k, v in dict(rows[1].get("headers") or {}).items()}
    return agenthub_headers, codex_headers


def _load_runtime_provider_request_target(
    config_toml: Path | None,
    auth_json: Path | None,
    *,
    cli_root: Path | None = None,
) -> tuple[str, str]:
    if config_toml is not None or auth_json is not None:
        if config_toml is None or auth_json is None:
            raise RuntimeError("config_toml and auth_json overrides must be provided together")
        config = tomllib.loads(config_toml.read_text())
        provider_name = str(config.get("model_provider") or "").strip() or "openai"
        provider_block = dict((config.get("model_providers") or {}).get(provider_name) or {})
        base_url = str(provider_block.get("base_url") or "").strip()
        if not base_url:
            raise RuntimeError(f"missing base_url for provider {provider_name!r} in {config_toml}")
        auth = json.loads(auth_json.read_text())
        api_key = str(auth.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError(f"missing OPENAI_API_KEY in {auth_json}")
        return base_url.rstrip("/") + "/responses", api_key

    snapshot = load_script_provider_management_snapshot(cwd=cli_root or _default_cli_root())
    selected = snapshot.selected_config
    if selected is None:
        raise RuntimeError("provider management did not resolve an active provider config")
    wire_api = str(selected.wire_api or "").strip().lower()
    planner_kind = str(selected.planner_kind or "").strip().lower()
    if wire_api != "responses" and planner_kind != "openai_responses":
        raise RuntimeError(
            "resolved provider config is not OpenAI Responses-compatible; "
            "pass --config-toml/--auth-json to target the replay endpoint explicitly"
        )
    base_url = str(selected.base_url or DEFAULT_OPENAI_BASE_URL).strip() or DEFAULT_OPENAI_BASE_URL
    api_key = str(selected.api_key or "").strip()
    if not api_key:
        raise RuntimeError(f"missing api_key in resolved provider config from {snapshot.resolution.auth_path}")
    return base_url.rstrip("/") + "/responses", api_key
