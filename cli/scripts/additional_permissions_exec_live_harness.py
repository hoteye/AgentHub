#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy


DEFAULT_JUSTIFICATION = "Need sandboxed writable temp access for an additional_permissions smoke test."


def _agenthub_config(base_url: str, model: str, effort: str) -> str:
    return (
        f'model_provider = "openai"\n'
        f'model = "{model}"\n'
        f'model_reasoning_effort = "{effort}"\n'
        'disable_response_storage = true\n'
        'preferred_auth_method = "apikey"\n'
        'approvals_reviewer = "user"\n'
        "\n"
        "[features.provider_discovery]\n"
        'strict_isolation = true\n'
        "\n"
        "[model_providers.openai]\n"
        'name = "openai"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'default_model = "gpt_54"\n'
        "\n"
        "[models.gpt_54]\n"
        'provider = "openai"\n'
        f'model_id = "{model}"\n'
        f'display_name = "{model}"\n'
        'planner_kind = "openai_responses"\n'
        'wire_api = "responses"\n'
        'supports_tools = true\n'
        'supports_reasoning = true\n'
        'interaction_profile = "codex_openai"\n'
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _tool_event_to_dict(event: Any) -> dict[str, Any]:
    return {
        "name": str(getattr(event, "name", "") or ""),
        "ok": bool(getattr(event, "ok", False)),
        "summary": str(getattr(event, "summary", "") or ""),
        "payload": dict(getattr(event, "payload", {}) or {}),
    }


def _to_dict(item: Any) -> dict[str, Any]:
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        return dict(value or {}) if isinstance(value, dict) else {}
    if isinstance(item, dict):
        return dict(item)
    return {}


def _prompt_response_to_dict(response: Any) -> dict[str, Any]:
    return {
        "assistant_text": str(getattr(response, "assistant_text", "") or ""),
        "commentary_text": str(getattr(response, "commentary_text", "") or ""),
        "tool_events": [_tool_event_to_dict(item) for item in list(getattr(response, "tool_events", []) or [])],
        "item_events": list(getattr(response, "item_events", []) or []),
        "turn_events": list(getattr(response, "turn_events", []) or []),
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _find_tool_event(items: list[Any], name: str) -> Any:
    for item in items:
        if str(getattr(item, "name", "") or "").strip() == name:
            return item
    raise AssertionError(f"missing tool event: {name}")


def _prompt_for_additional_permissions(additional_permissions: dict[str, Any]) -> str:
    payload_json = json.dumps(additional_permissions, ensure_ascii=True, sort_keys=True)
    return (
        "Call the exec_command tool exactly once. "
        'Use cmd="python -V". '
        'Use sandbox_permissions="with_additional_permissions". '
        f"Use additional_permissions={payload_json}. "
        f'Use justification="{DEFAULT_JUSTIFICATION}". '
        'Use prefix_rule=["python","-V"]. '
        "Use yield_time_ms=250 and max_output_tokens=200. "
        "Do not call any other tool. Do not answer in plain text."
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exercise additional_permissions through provider planning, approval, and replay.",
    )
    parser.add_argument("--auth-json", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--out-dir", default="")
    return parser


def run_probe(*, auth_json: Path, base_url: str, model: str, effort: str, out_dir: Path) -> dict[str, Any]:
    provider_home = out_dir / "provider_home"
    workspace = out_dir / "workspace"
    provider_home.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copy2(auth_json, provider_home / "auth.json")
    (provider_home / "config.toml").write_text(
        _agenthub_config(base_url, model, effort),
        encoding="utf-8",
    )

    os.environ["AGENTHUB_PROVIDER_HOME"] = str(provider_home)
    os.environ["AGENTHUB_PROVIDER_STRICT_ISOLATION"] = "1"

    additional_permissions = {
        "file_system": {
            "write": [str((workspace / "granted-output").resolve())],
        }
    }
    runtime = AgentCliRuntime(
        runtime_policy=RuntimePolicy.normalized(approval_policy="on-request"),
    )
    runtime.set_cwd(workspace)
    prompt = _prompt_for_additional_permissions(additional_permissions)
    initial_response = runtime.handle_prompt(prompt)
    initial_payload = _prompt_response_to_dict(initial_response)

    approval_event = _find_tool_event(list(getattr(initial_response, "tool_events", []) or []), "shell_approval_requested")
    approval_event_payload = dict(getattr(approval_event, "payload", {}) or {})
    approval_id = str(approval_event_payload.get("approval_id") or "").strip()
    function_call_arguments = dict(approval_event_payload.get("function_call_arguments") or {})
    action_policy = dict(approval_event_payload.get("action_policy") or {})

    _require(approval_id != "", "shell approval request did not include approval_id")
    _require(
        approval_event_payload.get("additional_permissions") == additional_permissions,
        "approval event lost additional_permissions payload: "
        f"approval_event.additional_permissions={_compact_json(approval_event_payload.get('additional_permissions'))} "
        f"function_call_arguments.additional_permissions={_compact_json(function_call_arguments.get('additional_permissions'))}",
    )
    _require(
        function_call_arguments.get("additional_permissions") == additional_permissions,
        "function_call_arguments lost additional_permissions payload: "
        f"function_call_arguments.additional_permissions={_compact_json(function_call_arguments.get('additional_permissions'))} "
        f"provider_command={_compact_json(approval_event_payload.get('command'))}",
    )
    _require(
        str(function_call_arguments.get("sandbox_permissions") or "") == "with_additional_permissions",
        "function_call_arguments lost sandbox_permissions=with_additional_permissions: "
        f"function_call_arguments.sandbox_permissions={_compact_json(function_call_arguments.get('sandbox_permissions'))}",
    )
    _require(
        dict(action_policy.get("metadata") or {}).get("requested_additional_permissions") == additional_permissions,
        "approval event action_policy snapshot lost requested_additional_permissions: "
        f"action_policy.metadata={_compact_json(action_policy.get('metadata'))}",
    )

    approval_ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)
    _require(approval_ticket is not None, "approval ticket was not persisted")
    action_request = runtime.gateway_state_store.get_action_request(getattr(approval_ticket, "action_id", "") or "")
    _require(action_request is not None, "action request was not persisted")
    approval_ticket_payload = _to_dict(approval_ticket)
    action_request_payload = _to_dict(action_request)

    _require(
        dict(approval_ticket_payload.get("metadata") or {}).get("additional_permissions") == additional_permissions,
        "approval ticket metadata lost additional_permissions",
    )
    _require(
        dict(dict(approval_ticket_payload.get("metadata") or {}).get("action_policy") or {}).get("metadata", {}).get(
            "requested_additional_permissions"
        )
        == additional_permissions,
        "approval ticket action_policy snapshot lost requested_additional_permissions",
    )
    _require(
        dict(action_request_payload.get("payload") or {}).get("additional_permissions") == additional_permissions,
        "action request payload lost additional_permissions",
    )

    decision = runtime.decide_approval(
        approval_id,
        approved=True,
        decided_by="live-harness",
    )
    decision_tool_events = list(decision.get("tool_events") or [])
    replay_shell_event = None
    for item in decision_tool_events:
        name = str(getattr(item, "name", "") or "").strip()
        if name in {"shell", "shell_start"}:
            replay_shell_event = item
            break
    _require(replay_shell_event is not None, "approval replay did not execute shell action")
    decision_action_request = _to_dict(decision.get("action_request"))
    _require(
        dict(decision_action_request.get("payload") or {}).get("additional_permissions") == additional_permissions,
        "approval replay response lost action_request.additional_permissions",
    )

    result = {
        "status": "passed",
        "prompt": prompt,
        "provider_home": str(provider_home),
        "workspace": str(workspace),
        "requested_additional_permissions": additional_permissions,
        "initial_response": initial_payload,
        "approval_ticket": approval_ticket_payload,
        "action_request": action_request_payload,
        "decision_response": {
            "approval_ticket": _to_dict(decision.get("approval_ticket")),
            "action_request": decision_action_request,
            "action_result": decision.get("action_result"),
            "tool_events": [_tool_event_to_dict(item) for item in decision_tool_events],
            "audit_records": [_to_dict(item) for item in list(decision.get("audit_records") or [])],
        },
        "replay_shell_event": _tool_event_to_dict(replay_shell_event),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    auth_json = Path(str(args.auth_json or "")).expanduser().resolve()
    out_dir = (
        Path(str(args.out_dir or "")).expanduser().resolve()
        if str(args.out_dir or "").strip()
        else Path.cwd() / "artifacts" / "additional_permissions_exec_live"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_probe(
            auth_json=auth_json,
            base_url=str(args.base_url or ""),
            model=str(args.model or ""),
            effort=str(args.effort or ""),
            out_dir=out_dir,
        )
    except Exception as exc:
        result = {
            "status": "failed",
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "out_dir": str(out_dir),
        }
        _write_json(out_dir / "summary.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    _write_json(out_dir / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
