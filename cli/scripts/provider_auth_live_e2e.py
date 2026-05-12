from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli.agent_cli.runtime import AgentCliRuntime


def _assistant_text(payload: Any) -> str:
    return str(getattr(payload, "assistant_text", "") or "").strip()


def _run_slash(runtime: AgentCliRuntime, command: str) -> str:
    result = runtime._run_command_text_result(command)
    return _assistant_text(result)


def _parse_key_values(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = str(raw_line or "").strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        mapping[str(key or "").strip()] = str(value or "").strip()
    return mapping


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live provider auth E2E flow: connect -> auth -> call -> refresh -> logout")
    parser.add_argument("--cwd", default=".", help="Workspace root for project-local provider config/auth files.")
    parser.add_argument("--provider", required=True, help="Provider name, e.g. openai/custom.")
    parser.add_argument("--model", required=True, help="Model selector used by /connect.")
    parser.add_argument("--base-url", required=True, help="Provider base URL used by /connect.")
    parser.add_argument(
        "--auth-mode",
        default="wellknown",
        choices=["api_key", "oauth", "wellknown", "none"],
        help="Provider auth mode for /connect.",
    )
    parser.add_argument("--api-key-env", default="", help="Required when --auth-mode api_key.")
    parser.add_argument(
        "--login-mode",
        default="browser_pkce",
        choices=["device_code", "browser_pkce"],
        help="Login mode for /auth login.",
    )
    parser.add_argument(
        "--wait-callback",
        action="store_true",
        help="For browser_pkce: start local callback listener and auto-exchange authorization code.",
    )
    parser.add_argument(
        "--callback-timeout-seconds",
        type=int,
        default=180,
        help="Timeout used with --wait-callback.",
    )
    parser.add_argument(
        "--auth-code",
        default="",
        help="Manual authorization code for browser_pkce exchange when callback automation is not used.",
    )
    parser.add_argument("--state", default="", help="Optional returned state for browser_pkce code exchange.")
    parser.add_argument(
        "--call-prompt",
        default="请回复 E2E-OK。",
        help="One real prompt executed after successful auth.",
    )
    parser.add_argument(
        "--write-scope",
        default="project",
        choices=["project", "user"],
        help="Where /connect writes config.toml.",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    cwd = Path(str(args.cwd or ".")).resolve()
    runtime = AgentCliRuntime()
    runtime.set_cwd(cwd)

    connect_cmd_parts = [
        "/connect",
        f"--provider {args.provider}",
        f"--model {args.model}",
        f"--base-url {args.base_url}",
        f"--auth-mode {args.auth_mode}",
        f"--write {args.write_scope}",
    ]
    if args.auth_mode == "api_key":
        if not str(args.api_key_env or "").strip():
            raise SystemExit("--api-key-env is required when --auth-mode api_key")
        connect_cmd_parts.append(f"--api-key-env {args.api_key_env}")
    connect_text = _run_slash(runtime, " ".join(connect_cmd_parts))

    status_text_before = _run_slash(runtime, f"/auth status --provider {args.provider}")

    login_text = ""
    if args.auth_mode in {"oauth", "wellknown"}:
        login_parts = [
            "/auth login",
            f"--provider {args.provider}",
            f"--mode {args.login_mode}",
        ]
        if args.login_mode == "browser_pkce":
            if args.wait_callback:
                login_parts.append("--wait-callback")
                login_parts.append(f"--callback-timeout-seconds {int(args.callback_timeout_seconds)}")
            elif str(args.auth_code or "").strip():
                login_parts.append(f"--auth-code {args.auth_code}")
                if str(args.state or "").strip():
                    login_parts.append(f"--state {args.state}")
        login_text = _run_slash(runtime, " ".join(login_parts))
        if args.login_mode == "device_code":
            first_map = _parse_key_values(login_text)
            if str(first_map.get("auth_status") or "") == "authorization_pending":
                login_text = _run_slash(
                    runtime,
                    f"/auth login --provider {args.provider} --mode device_code --poll",
                )
        elif args.login_mode == "browser_pkce" and not args.wait_callback and not str(args.auth_code or "").strip():
            raise SystemExit(
                "browser_pkce requires one of: --wait-callback or --auth-code <code>. "
                "Run once with --wait-callback, or supply a code from your OAuth callback."
            )

    provider_switch_text = _run_slash(runtime, f"/provider {args.provider}")
    prompt_result = runtime.handle_prompt(str(args.call_prompt))
    call_text = _assistant_text(prompt_result)
    refresh_text = _run_slash(runtime, f"/auth refresh --provider {args.provider}")
    logout_text = _run_slash(runtime, f"/auth logout --provider {args.provider}")
    status_text_after = _run_slash(runtime, f"/auth status --provider {args.provider}")

    print(
        json.dumps(
            {
                "cwd": str(cwd),
                "provider": args.provider,
                "connect": connect_text,
                "auth_status_before": status_text_before,
                "auth_login": login_text,
                "provider_switch": provider_switch_text,
                "call_assistant_text": call_text,
                "tool_events": [
                    {
                        "name": str(event.name or ""),
                        "ok": bool(event.ok),
                        "summary": str(event.summary or ""),
                    }
                    for event in list(getattr(prompt_result, "tool_events", []) or [])
                ],
                "auth_refresh": refresh_text,
                "auth_logout": logout_text,
                "auth_status_after": status_text_after,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
