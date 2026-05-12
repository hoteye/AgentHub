from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.host_platform import HostPlatform

_BACKGROUND_SESSION_YIELD_TIME_MS = 250
_CLAUDE_STYLE_AUTO_BACKGROUND_THRESHOLD_MS = 15_000


def quote_value(value: Any, quote_arg_fn: Callable[[Any], str]) -> str:
    return quote_arg_fn(str(value))


def normalized_tool_name(name: str) -> str:
    return str(name or "").strip().lower()


def shell_override_for_tool_name(name: str) -> str | None:
    normalized = normalized_tool_name(name)
    if normalized == "bash":
        return "bash"
    if normalized == "powershell":
        return "powershell"
    return None


def optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def uses_claude_style_auto_background(tool_name: str) -> bool:
    return normalized_tool_name(tool_name) in {"bash", "powershell"}


def normalized_shell_yield_time_ms(arguments: dict[str, Any], *, tool_name: str = "") -> Any:
    explicit = arguments.get("yield_time_ms")
    if explicit is not None:
        return explicit
    if optional_bool(arguments.get("run_in_background")) is True:
        return _BACKGROUND_SESSION_YIELD_TIME_MS
    if uses_claude_style_auto_background(tool_name):
        return _CLAUDE_STYLE_AUTO_BACKGROUND_THRESHOLD_MS
    return None


def normalized_shell_timeout_ms(arguments: dict[str, Any]) -> Any:
    explicit = arguments.get("timeout_ms")
    if explicit is not None:
        return explicit
    return arguments.get("timeout")


def shell_family(shell: Any) -> str | None:
    raw = str(shell or "").strip()
    if not raw:
        return None
    normalized = raw.replace("\\", "/").rstrip("/")
    base = normalized.rsplit("/", 1)[-1].lower()
    if base.endswith(".exe"):
        base = base[:-4]
    if base == "posix":
        return "posix"
    if base in {"bash", "sh", "zsh"}:
        return "posix"
    if base in {"powershell", "pwsh"}:
        return "powershell"
    return None


def normalized_exec_command(
    raw_command: Any,
    host_platform: HostPlatform,
    *,
    explicit_shell: str | None = None,
) -> str:
    command = str(raw_command or "").strip()
    if not command:
        return ""
    if shell_family(explicit_shell) is not None:
        return command
    return host_platform.normalize_shell_command(command)


def build_exec_command(
    raw_command: Any,
    *,
    workdir: Any,
    shell: Any,
    tty: Any,
    login: Any,
    yield_time_ms: Any,
    timeout_ms: Any,
    max_output_tokens: Any,
    host_platform: HostPlatform,
    quote_arg_fn: Callable[[Any], str],
) -> str | None:
    explicit_shell = str(shell or "").strip() or None
    normalized = normalized_exec_command(
        raw_command,
        host_platform,
        explicit_shell=explicit_shell,
    )
    if not normalized:
        return None
    command = f"/exec_command {quote_arg_fn(normalized)}"
    normalized_workdir = str(workdir or "").strip()
    if normalized_workdir:
        command += f" --workdir {quote_arg_fn(normalized_workdir)}"
    if explicit_shell:
        command += f" --shell {quote_arg_fn(explicit_shell)}"
    if tty is True:
        command += " --tty"
    if login is not None:
        command += f" --login {quote_arg_fn(str(bool(login)).lower())}"
    if yield_time_ms is not None:
        command += f" --yield-time-ms {quote_value(yield_time_ms, quote_arg_fn)}"
    if timeout_ms is not None:
        command += f" --timeout-ms {quote_value(timeout_ms, quote_arg_fn)}"
    if max_output_tokens is not None:
        command += f" --max-output-tokens {quote_value(max_output_tokens, quote_arg_fn)}"
    return command


def normalized_collab_items(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list | tuple):
        return None
    normalized: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item_type = str(item.get("type") or "").strip().lower()
        if not item_type:
            continue
        item["type"] = item_type
        if item_type == "image":
            image_url = str(item.get("image_url") or item.get("url") or "").strip()
            if image_url:
                item["image_url"] = image_url
                item.pop("url", None)
        normalized.append(item)
    return normalized or None


def collab_item_preview(item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "text":
        return str(item.get("text") or "").strip()
    if item_type == "image":
        return "[image]"
    if item_type in {"local_image", "localimage"}:
        path = str(item.get("path") or "").strip()
        return f"[local_image:{path}]" if path else "[local_image]"
    if item_type == "skill":
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        if name and path:
            return f"[skill:${name}]({path})"
        return "[skill]"
    if item_type == "mention":
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        if name and path:
            return f"[mention:${name}]({path})"
        if name:
            return f"@{name}"
        return "[mention]"
    return "[input]"


def collab_items_preview(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    previews = [collab_item_preview(item) for item in items]
    return "\n".join(text for text in previews if text).strip()


def uses_legacy_spawn_agent_payload(arguments: dict[str, Any]) -> bool:
    return any(
        key in arguments
        for key in (
            "task",
            "role",
            "model",
            "provider",
            "reasoning_effort",
            "timeout",
            "async",
            "reason",
            "mode",
            "wait_required",
            "task_shape",
            "subagent_type",
        )
    )
