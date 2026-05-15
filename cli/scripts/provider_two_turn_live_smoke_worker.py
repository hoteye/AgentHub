from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import (
        apply_provider_home_override_env,
        ensure_script_import_paths,
        normalize_optional_provider_home_override,
        resolve_effective_script_provider_home_dir,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import (  # type: ignore[no-redef]
        apply_provider_home_override_env,
        ensure_script_import_paths,
        normalize_optional_provider_home_override,
        resolve_effective_script_provider_home_dir,
    )


_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
FIRST_PROMPT_TEMPLATE = (
    "上线前 provider live smoke。请记住检查码 {token}。" "只回复 READY。不要使用工具。"
)
SECOND_PROMPT = "请只回复刚才我让你记住的检查码。不要解释，不要使用工具。"


@dataclass(frozen=True)
class WorkerProviderCase:
    provider: str
    model: str

    def env_overrides(self, *, provider_home: str = "") -> dict[str, str]:
        env = {
            "AGENT_CLI_PROVIDER": self.provider,
            "AGENT_CLI_MODEL": self.model,
        }
        return apply_provider_home_override_env(env, provider_home=provider_home)


def _provider_home_report_fields(provider_home: str) -> dict[str, str]:
    normalized = normalize_optional_provider_home_override(provider_home)
    return {
        "provider_home": str(
            resolve_effective_script_provider_home_dir(
                cwd=CLI_ROOT,
                provider_home=normalized,
            )
        ),
        "provider_home_override": normalized,
        "provider_home_source": "explicit_override" if normalized else "runtime_default",
    }


def _tool_name(item: Any) -> str:
    value = getattr(item, "name", "")
    if value:
        return str(value)
    payload = getattr(item, "payload", None)
    if isinstance(payload, dict):
        return str(payload.get("name") or payload.get("tool_name") or "")
    return ""


def _response_payload(
    *,
    prompt: str,
    response: Any,
    tool_name_fn: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    resolve_tool_name = tool_name_fn or _tool_name
    assistant_text = str(getattr(response, "assistant_text", "") or "")
    status = dict(getattr(response, "status", {}) or {})
    timings = dict(getattr(response, "timings", {}) or {})
    diagnostics = dict(getattr(response, "protocol_diagnostics", {}) or {})
    protocol_path = dict(diagnostics.get("protocol_path") or {})
    tool_events = list(getattr(response, "tool_events", []) or [])
    return {
        "prompt": prompt,
        "assistant_text": assistant_text,
        "assistant_preview": assistant_text.replace("\n", " ")[:240],
        "provider_runtime_state": status.get("provider_runtime_state"),
        "provider_name": status.get("provider_name"),
        "provider_model": status.get("provider_model"),
        "provider_label": status.get("provider_label"),
        "protocol_path_kind": protocol_path.get("kind"),
        "provider_used": protocol_path.get("provider_used"),
        "tool_event_count": len(tool_events),
        "tool_names": [name for item in tool_events if (name := resolve_tool_name(item))],
        "initial_model_ms": timings.get("initial_model_ms"),
        "total_ms": timings.get("total_ms"),
        "planning_rounds": timings.get("planning_rounds"),
    }


def _fallback_detected(turn: dict[str, Any]) -> bool:
    text = str(turn.get("assistant_text") or "")
    return (
        str(turn.get("protocol_path_kind") or "") == "provider_degraded_fallback"
        or "当前 provider 调用失败" in text
        or "provider 调用失败" in text
        or text.startswith("无法继续：")
    )


def evaluate_case_health(
    payload: dict[str, Any],
    *,
    fallback_detected_fn: Callable[[dict[str, Any]], bool] | None = None,
) -> str:
    detect_fallback = fallback_detected_fn or _fallback_detected
    if payload.get("timeout") or payload.get("parse_error") or payload.get("exception"):
        return "error"
    if payload.get("provider_runtime_state") != "ready":
        return "error"
    turns = list(payload.get("turns") or [])
    if len(turns) != 2:
        return "error"
    if any(not str(turn.get("assistant_text") or "").strip() for turn in turns):
        return "error"
    if any(detect_fallback(turn) for turn in turns):
        return "error"
    if any(turn.get("provider_used") is False for turn in turns):
        return "error"
    token = str(payload.get("token") or "").strip()
    second_text = str(turns[1].get("assistant_text") or "")
    if token and token not in second_text:
        return "error"
    if any(int(turn.get("tool_event_count") or 0) > 0 for turn in turns):
        return "warning"
    return "ok"


def _summary_for_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(results),
        "ok": sum(1 for item in results if item.get("health") == "ok"),
        "warning": sum(1 for item in results if item.get("health") == "warning"),
        "error": sum(1 for item in results if item.get("health") == "error"),
    }


def _run_worker(
    args: argparse.Namespace,
    *,
    provider_case_factory: Callable[..., Any] = WorkerProviderCase,
    provider_home_report_fields_fn: Callable[[str], dict[str, str]] = _provider_home_report_fields,
    first_prompt_template: str = FIRST_PROMPT_TEMPLATE,
    second_prompt: str = SECOND_PROMPT,
    response_payload_fn: Callable[..., dict[str, Any]] = _response_payload,
    evaluate_case_health_fn: Callable[[dict[str, Any]], str] = evaluate_case_health,
) -> int:
    from cli.agent_cli.runtime import AgentCliRuntime
    from cli.agent_cli.runtime_policy import RuntimePolicy

    case = provider_case_factory(
        provider=str(args.provider or "").strip(),
        model=str(args.model or "").strip(),
    )
    if not case.provider or not case.model:
        raise SystemExit("worker requires --provider and --model")

    provider_home = normalize_optional_provider_home_override(args.provider_home)
    previous_env = {
        key: os.environ.get(key) for key in case.env_overrides(provider_home=provider_home)
    }
    try:
        os.environ.update(case.env_overrides(provider_home=provider_home))
        token = str(args.token or "").strip()
        first_prompt = first_prompt_template.format(token=token)
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "provider": case.provider,
            "model": case.model,
            "token": token,
            **provider_home_report_fields_fn(provider_home),
        }
        runtime = AgentCliRuntime(
            runtime_policy=RuntimePolicy.normalized(
                approval_policy="never",
                sandbox_mode="workspace-write",
                web_search_mode="disabled",
                network_access_enabled=False,
            )
        )
        first_response = runtime.handle_prompt(first_prompt)
        second_response = runtime.handle_prompt(second_prompt)
        provider_status = dict(runtime.agent.provider_status() or {})
        payload.update(
            {
                "provider_runtime_state": provider_status.get("provider_runtime_state"),
                "provider_name": provider_status.get("provider_name"),
                "provider_model": provider_status.get("provider_model"),
                "provider_label": provider_status.get("provider_label"),
                "turns": [
                    response_payload_fn(prompt=first_prompt, response=first_response),
                    response_payload_fn(prompt=second_prompt, response=second_response),
                ],
            }
        )
        payload["health"] = evaluate_case_health_fn(payload)
        payload["wall_ms"] = int((time.perf_counter() - started) * 1000)
    except Exception as exc:
        payload = {
            "provider": case.provider,
            "model": case.model,
            "token": str(args.token or "").strip(),
            "health": "error",
            "exception": f"{type(exc).__name__}: {exc}",
        }
    finally:
        for key, old_value in previous_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
    print(json.dumps(payload, ensure_ascii=False))
    return 0
