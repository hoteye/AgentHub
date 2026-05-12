from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    from cli.scripts.benchmark_emptydir_ab_model_io_helpers import (
        CommandResult,
        RunSummary,
        _iso_now,
        _write_text,
    )
    from cli.scripts.script_runtime_helpers import (
        apply_provider_home_override_env,
        ensure_script_import_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_emptydir_ab_model_io_helpers import (  # type: ignore[no-redef]
        CommandResult,
        RunSummary,
        _iso_now,
        _write_text,
    )
    from script_runtime_helpers import (  # type: ignore[no-redef]
        apply_provider_home_override_env,
        ensure_script_import_paths,
    )

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
REPO_ROOT = _SCRIPT_PATHS.cli_root
DEFAULT_AGENTHUB_MAIN = REPO_ROOT / "agent_cli" / "__main__.py"
DEFAULT_CODEX_REF_ROOT = Path("/home/lyc/project/AgentHubRef/codex_ref")
DEFAULT_CODEX_BIN = DEFAULT_CODEX_REF_ROOT / "codex-rs" / "target" / "debug" / "codex"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def parse_args(
    *,
    default_base_url: str = DEFAULT_BASE_URL,
    default_codex_bin: Path = DEFAULT_CODEX_BIN,
    default_agenthub_main: Path = DEFAULT_AGENTHUB_MAIN,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AgentHub and codex_ref headless in separate empty workspaces.",
    )
    parser.add_argument("--prompt-file", required=True, help="Prompt file to replay.")
    parser.add_argument("--out-dir", help="Output directory. Defaults to a temp dir.")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="")
    parser.add_argument("--openai-base-url", default=default_base_url)
    parser.add_argument("--codex-config-mode", choices=("home", "ephemeral"), default="home")
    parser.add_argument(
        "--codex-provider-id",
        default="",
        help="Optional Codex provider id used when building ephemeral config. Defaults to a safe value derived from --openai-base-url.",
    )
    parser.add_argument(
        "--codex-bin",
        default=str(default_codex_bin),
        help="Absolute path to the compiled codex_ref binary used for the Codex side of the harness.",
    )
    parser.add_argument("--api-key-name", default="OPENAI_API_KEY")
    parser.add_argument("--auth-json", default="")
    parser.add_argument("--agenthub-main", default=str(default_agenthub_main))
    parser.add_argument(
        "--agenthub-config-mode",
        choices=("home", "project_local"),
        default="home",
        help="Where AgentHub should read provider config from during the harness run.",
    )
    parser.add_argument(
        "--agenthub-interaction-profile",
        default="codex_openai",
        help="AgentHub interaction_profile written into project-local config. Defaults to codex_openai for Codex A/B runs.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--validation-timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--agenthub-network-access", choices=("enabled", "disabled"), default="disabled"
    )
    parser.add_argument(
        "--validate",
        default="",
        help="Optional validation command run in each workspace, e.g. 'pytest -q'.",
    )
    return parser.parse_args()


def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> CommandResult:
    started_at = _iso_now()
    start = time.perf_counter()
    timed_out = False
    stdout_text = ""
    stderr_text = ""
    exit_code = 0
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout
        stderr_text = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
    elapsed = time.perf_counter() - start
    ended_at = _iso_now()
    _write_text(stdout_path, stdout_text)
    _write_text(stderr_path, stderr_text)
    return CommandResult(
        name=name,
        command=list(command),
        cwd=str(cwd),
        exit_code=exit_code,
        elapsed_seconds=round(elapsed, 3),
        timed_out=timed_out,
        started_at=started_at,
        ended_at=ended_at,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def _run_validation(
    *,
    name: str,
    command_text: str,
    cwd: Path,
    env: dict[str, str],
    out_dir: Path,
    timeout_seconds: int,
) -> CommandResult:
    command = ["/bin/bash", "-lc", command_text]
    return _run_command(
        name=name,
        command=command,
        cwd=cwd,
        env=env,
        stdout_path=out_dir / f"{name}.stdout.log",
        stderr_path=out_dir / f"{name}.stderr.log",
        timeout_seconds=timeout_seconds,
    )


def _parse_agenthub_output(stdout_path: Path) -> str:
    if not stdout_path.exists():
        return ""
    text = stdout_path.read_text(encoding="utf-8").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    return str(payload.get("assistant_text") or "").strip()


def _parse_codex_output(stdout_path: Path) -> tuple[str, str, list[str]]:
    assistant_text = ""
    thread_id = ""
    errors: list[str] = []
    if not stdout_path.exists():
        return assistant_text, thread_id, errors
    for raw_line in stdout_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = str(event.get("type") or "")
        if event_type == "thread.started":
            thread_id = str(event.get("thread_id") or thread_id)
            continue
        if event_type == "error":
            message = str(event.get("message") or "").strip()
            if message:
                errors.append(message)
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type == "agent_message":
            assistant_text = str(item.get("text") or assistant_text).strip()
        elif item_type == "error":
            message = str(item.get("message") or "").strip()
            if message:
                errors.append(message)
    return assistant_text, thread_id, errors


def _build_codex_home(
    codex_home: Path,
    api_key: str,
    provider_id: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
    workspace: Path,
) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_payload = {
        "OPENAI_API_KEY": api_key,
        "tokens": None,
        "last_refresh": None,
    }
    _write_text(codex_home / "auth.json", json.dumps(auth_payload))
    normalized_provider = str(provider_id or "").strip() or "openai"
    config_lines = [
        f'model_provider = "{normalized_provider}"',
        f'model = "{model}"',
        "disable_response_storage = true",
        'approval_policy = "never"',
        'preferred_auth_method = "apikey"',
    ]
    if str(reasoning_effort or "").strip():
        config_lines.insert(2, f'model_reasoning_effort = "{reasoning_effort}"')
    if normalized_provider == "openai" and _is_official_openai_base_url(openai_base_url):
        config_lines.append(f'openai_base_url = "{openai_base_url}"')
    else:
        config_lines.extend(
            [
                "",
                f"[model_providers.{normalized_provider}]",
                f'name = "{normalized_provider}"',
                f'base_url = "{openai_base_url}"',
                'wire_api = "responses"',
            ]
        )
    config_lines.extend(
        [
            "",
            f'[projects."{workspace}"]',
            'trust_level = "trusted"',
        ]
    )
    _write_text(codex_home / "config.toml", "\n".join(config_lines) + "\n")


def _is_official_openai_base_url(base_url: str) -> bool:
    try:
        hostname = str(urlparse(base_url).hostname or "").strip().lower()
    except Exception:
        hostname = ""
    return hostname in {"api.openai.com"}


def _default_codex_provider_id(base_url: str) -> str:
    return "openai" if _is_official_openai_base_url(base_url) else "openai-relay"


def _build_agenthub_project_local_config(
    *,
    project_root: Path,
    api_key: str,
    provider: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
    interaction_profile: str,
) -> tuple[Path, Path]:
    config_dir = project_root / ".config"
    config_dir.mkdir(parents=True, exist_ok=True)
    auth_path = config_dir / "auth.json"
    config_path = config_dir / "config.toml"
    provider_key = str(provider or "openai").strip() or "openai"
    model_key = str(model or "gpt-5.4").strip() or "gpt-5.4"
    lines = [
        f'model_provider = "{provider_key}"',
        f'model = "{model_key}"',
        "",
        f"[model_providers.{provider_key}]",
        f'base_url = "{openai_base_url}"',
        'wire_api = "responses"',
        f'default_model = "{model_key}"',
        "",
        f'[models."{model_key}"]',
        f'provider = "{provider_key}"',
        f'model_id = "{model}"',
        'planner_kind = "openai_responses"',
        'wire_api = "responses"',
    ]
    if str(reasoning_effort or "").strip():
        lines.append(f'reasoning_effort = "{reasoning_effort}"')
    normalized_profile = str(interaction_profile or "").strip()
    if normalized_profile:
        lines.append(f'interaction_profile = "{normalized_profile}"')
    _write_text(config_path, "\n".join(lines) + "\n")
    _write_text(
        auth_path, json.dumps({"OPENAI_API_KEY": api_key}, ensure_ascii=False, indent=2) + "\n"
    )
    return config_path, auth_path


def _build_agenthub_env(
    *,
    common_env: dict[str, str],
    provider: str,
    model: str,
    reasoning_effort: str,
    openai_base_url: str,
    provider_home: Path,
    startup_cwd: Path,
    debug_log_dir: Path,
    agent_cli_home: Path | None = None,
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
    env["AGENT_CLI_PROVIDER"] = provider
    env["AGENT_CLI_MODEL"] = model
    if str(reasoning_effort or "").strip():
        env["AGENT_CLI_REASONING_EFFORT"] = reasoning_effort
    else:
        env.pop("AGENT_CLI_REASONING_EFFORT", None)
    apply_provider_home_override_env(env, provider_home=provider_home)
    env["AGENTHUB_STARTUP_CWD"] = str(startup_cwd)
    env["AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE"] = "1"
    env["AGENTHUB_STARTUP_CWD_SOURCE"] = "launcher"
    env["AGENTHUB_DEBUG_LOG_DIR"] = str(debug_log_dir)
    if agent_cli_home is not None:
        env["AGENT_CLI_HOME"] = str(agent_cli_home)
    return env


def _build_agenthub_home(
    *,
    agenthub_home: Path,
    codex_skills_home: Path = DEFAULT_CODEX_HOME,
) -> None:
    agenthub_home.mkdir(parents=True, exist_ok=True)
    source_skills_dir = codex_skills_home / "skills"
    target_skills_dir = agenthub_home / "skills"
    if not source_skills_dir.is_dir():
        return
    shutil.copytree(source_skills_dir, target_skills_dir, dirs_exist_ok=True)


def _print_summary(summary: RunSummary) -> None:
    print(f"harness_root={summary.harness_root}")
    print(f"prompt_path={summary.prompt_path}")
    print(f"provider={summary.provider}")
    print(f"model={summary.model}")
    print(f"openai_base_url={summary.openai_base_url}")
    print(f"codex_config_mode={summary.codex_config_mode}")
    print(f"codex_provider_id={summary.codex_provider_id}")
    print(f"codex_bin={summary.codex_bin}")
    print(f"codex_config_path={summary.codex_config_path}")
    print(
        "agenthub:"
        f" exit={summary.agenthub_run['exit_code']}"
        f" elapsed={summary.agenthub_run['elapsed_seconds']}s"
        f" validation={summary.agenthub_validation['exit_code'] if summary.agenthub_validation else '-'}"
    )
    print(
        "codex:"
        f" exit={summary.codex_run['exit_code']}"
        f" elapsed={summary.codex_run['elapsed_seconds']}s"
        f" validation={summary.codex_validation['exit_code'] if summary.codex_validation else '-'}"
    )
    if summary.agenthub_assistant_text:
        print(f"agenthub_assistant_text={summary.agenthub_assistant_text[:240]}")
    if summary.codex_assistant_text:
        print(f"codex_assistant_text={summary.codex_assistant_text[:240]}")
    if summary.codex_thread_id:
        print(f"codex_thread_id={summary.codex_thread_id}")
    if summary.codex_errors:
        print("codex_errors=" + " | ".join(summary.codex_errors[:4]))
    print(
        "layers:"
        f" request_raw.instructions_equal={summary.layer_summary['request_raw']['instructions_equal']}"
        f" tool_schema.agenthub_only={len(summary.layer_summary['tool_schema']['agenthub_only'])}"
        f" tool_call_chain.sequence_equal={summary.layer_summary['tool_call_chain']['tool_name_sequence_equal']}"
        f" workspace.visible_files_equal={summary.layer_summary['workspace_side_effects']['visible_files_equal']}"
    )
    print(f"log_manifest={summary.log_manifest['commands']}")
