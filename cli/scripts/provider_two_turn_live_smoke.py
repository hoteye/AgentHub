#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
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
DEFAULT_CASES = (
    ("openai", "gpt_54"),
    ("anthropic", "claude_sonnet_46"),
)
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_WORKERS = 2
FIRST_PROMPT_TEMPLATE = (
    "上线前 provider live smoke。请记住检查码 {token}。" "只回复 READY。不要使用工具。"
)
SECOND_PROMPT = "请只回复刚才我让你记住的检查码。不要解释，不要使用工具。"


@dataclass(frozen=True)
class ProviderCase:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    def env_overrides(self, *, provider_home: str = "") -> dict[str, str]:
        env = {
            "AGENT_CLI_PROVIDER": self.provider,
            "AGENT_CLI_MODEL": self.model,
        }
        return apply_provider_home_override_env(env, provider_home=provider_home)


def parse_case(value: str) -> ProviderCase:
    text = str(value or "").strip()
    provider, sep, model = text.partition(":")
    if not sep or not provider.strip() or not model.strip():
        raise argparse.ArgumentTypeError(f"invalid --case {value!r}; expected provider:model")
    return ProviderCase(provider=provider.strip(), model=model.strip())


def default_cases() -> list[ProviderCase]:
    return [ProviderCase(provider=provider, model=model) for provider, model in DEFAULT_CASES]


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


def _token_for_case(case: ProviderCase, *, run_id: str) -> str:
    provider = case.provider.replace("_", "-")
    model = case.model.replace("_", "-")
    return f"AGENTHUB-LIVE-SMOKE-{run_id}-{provider}-{model}"


def _tool_name(item: Any) -> str:
    value = getattr(item, "name", "")
    if value:
        return str(value)
    payload = getattr(item, "payload", None)
    if isinstance(payload, dict):
        return str(payload.get("name") or payload.get("tool_name") or "")
    return ""


def _response_payload(*, prompt: str, response: Any) -> dict[str, Any]:
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
        "tool_names": [name for item in tool_events if (name := _tool_name(item))],
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


def evaluate_case_health(payload: dict[str, Any]) -> str:
    if payload.get("timeout") or payload.get("parse_error") or payload.get("exception"):
        return "error"
    if payload.get("provider_runtime_state") != "ready":
        return "error"
    turns = list(payload.get("turns") or [])
    if len(turns) != 2:
        return "error"
    if any(not str(turn.get("assistant_text") or "").strip() for turn in turns):
        return "error"
    if any(_fallback_detected(turn) for turn in turns):
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


def _common_worker_command(
    case: ProviderCase,
    *,
    token: str,
    provider_home: str,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--provider",
        case.provider,
        "--model",
        case.model,
        "--token",
        token,
    ]
    normalized = normalize_optional_provider_home_override(provider_home)
    if normalized:
        command.extend(["--provider-home", normalized])
    return command


def _run_worker(args: argparse.Namespace) -> int:
    from cli.agent_cli.runtime import AgentCliRuntime
    from cli.agent_cli.runtime_policy import RuntimePolicy

    case = ProviderCase(
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
        first_prompt = FIRST_PROMPT_TEMPLATE.format(token=token)
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "provider": case.provider,
            "model": case.model,
            "token": token,
            **_provider_home_report_fields(provider_home),
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
        second_response = runtime.handle_prompt(SECOND_PROMPT)
        provider_status = dict(runtime.agent.provider_status() or {})
        payload.update(
            {
                "provider_runtime_state": provider_status.get("provider_runtime_state"),
                "provider_name": provider_status.get("provider_name"),
                "provider_model": provider_status.get("provider_model"),
                "provider_label": provider_status.get("provider_label"),
                "turns": [
                    _response_payload(prompt=first_prompt, response=first_response),
                    _response_payload(prompt=SECOND_PROMPT, response=second_response),
                ],
            }
        )
        payload["health"] = evaluate_case_health(payload)
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


def _decode_worker_payload(stdout_text: str) -> dict[str, Any]:
    raw_text = str(stdout_text or "")
    decoder = json.JSONDecoder()
    candidates: list[str] = []
    if raw_text.strip():
        candidates.append(raw_text)
    lines = raw_text.splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith("{"):
            candidates.append("\n".join(lines[index:]))

    seen: set[str] = set()
    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        stripped = candidate.lstrip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        try:
            payload, _end = decoder.raw_decode(stripped)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(payload, dict):
            return payload
    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("expected JSON object output", raw_text, 0)


def _run_case_subprocess(
    case: ProviderCase,
    *,
    token: str,
    timeout_seconds: float,
    provider_home: str,
) -> dict[str, Any]:
    command = _common_worker_command(case, token=token, provider_home=provider_home)
    env = dict(os.environ)
    env.update(case.env_overrides(provider_home=provider_home))
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(CLI_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "provider": case.provider,
            "model": case.model,
            "token": token,
            "health": "error",
            "timeout": True,
            "wall_ms": int((time.perf_counter() - started) * 1000),
            "stdout_preview": str(exc.stdout or "").strip()[:400],
            "stderr": str(exc.stderr or "").strip()[:400],
            "command": command,
        }

    result: dict[str, Any] = {
        "provider": case.provider,
        "model": case.model,
        "token": token,
        "exit_code": int(completed.returncode),
        "orchestrator_wall_ms": int((time.perf_counter() - started) * 1000),
        "stderr": completed.stderr.strip()[:400],
        "command": command,
    }
    try:
        payload = _decode_worker_payload(completed.stdout)
    except json.JSONDecodeError as exc:
        result["health"] = "error"
        result["parse_error"] = f"{type(exc).__name__}: {exc}"
        result["stdout_preview"] = completed.stdout.strip()[:400]
        return result

    payload.setdefault("command", command)
    payload["exit_code"] = int(completed.returncode)
    payload["worker_wall_ms"] = payload.get("wall_ms")
    payload["orchestrator_wall_ms"] = result["orchestrator_wall_ms"]
    if completed.returncode != 0:
        payload["health"] = "error"
        payload["stderr"] = result["stderr"]
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/provider_two_turn_live_smoke.py",
        description="Run a two-turn live provider continuity smoke across provider:model cases.",
    )
    parser.add_argument("--case", action="append", type=parse_case, dest="cases")
    parser.add_argument("--provider-home", default="")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--run-id", default=str(int(time.time())))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--provider", default="", help=argparse.SUPPRESS)
    parser.add_argument("--model", default="", help=argparse.SUPPRESS)
    parser.add_argument("--token", default="", help=argparse.SUPPRESS)
    return parser


def _orchestrate(args: argparse.Namespace) -> int:
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")
    if args.max_workers <= 0:
        raise SystemExit("--max-workers must be greater than zero")

    cases = list(args.cases or default_cases())
    run_id = str(args.run_id or "").strip() or str(int(time.time()))
    provider_home = str(args.provider_home or "")
    case_specs = [
        {
            "provider": case.provider,
            "model": case.model,
            "token": _token_for_case(case, run_id=run_id),
            "env": case.env_overrides(provider_home=provider_home),
            "command": _common_worker_command(
                case,
                token=_token_for_case(case, run_id=run_id),
                provider_home=provider_home,
            ),
        }
        for case in cases
    ]
    if args.dry_run:
        payload = {
            "cwd": str(CLI_ROOT),
            "run_id": run_id,
            **_provider_home_report_fields(provider_home),
            "timeout_seconds": float(args.timeout),
            "max_workers": int(args.max_workers),
            "cases": case_specs,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "Dry run")
        return 0

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(int(args.max_workers), len(cases))) as executor:
        future_map = {
            executor.submit(
                _run_case_subprocess,
                case,
                token=_token_for_case(case, run_id=run_id),
                timeout_seconds=float(args.timeout),
                provider_home=provider_home,
            ): case
            for case in cases
        }
        for future in as_completed(future_map):
            case = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "provider": case.provider,
                        "model": case.model,
                        "health": "error",
                        "exception": f"{type(exc).__name__}: {exc}",
                    }
                )

    results.sort(key=lambda item: (str(item.get("provider") or ""), str(item.get("model") or "")))
    report = {
        "run_id": run_id,
        **_provider_home_report_fields(provider_home),
        "timeout_seconds": float(args.timeout),
        "max_workers": int(args.max_workers),
        "orchestrator_wall_ms": int((time.perf_counter() - started) * 1000),
        "cases": case_specs,
        "results": results,
        "summary": _summary_for_results(results),
    }
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json
        else json.dumps(report["summary"], ensure_ascii=False)
    )
    return 1 if int(report["summary"]["error"]) > 0 else 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.worker:
        return _run_worker(args)
    return _orchestrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
