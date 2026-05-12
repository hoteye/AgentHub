from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys
from pathlib import Path

try:
    from cli.scripts.script_runtime_helpers import (
        apply_provider_home_override_env,
        normalize_optional_provider_home_override,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import (  # type: ignore[no-redef]
        apply_provider_home_override_env,
        normalize_optional_provider_home_override,
    )


DEFAULT_CASES = (
    ("claude", "claude-sonnet-4-6"),
    ("claude", "claude-haiku-4-5-20251001"),
    ("deepseek", "deepseek-chat"),
    ("glm-claude-mode", "glm-5"),
    ("openai", "gpt-5.4"),
    ("openai", "gpt-5.3-reference"),
)


@dataclass(frozen=True)
class BenchmarkCase:
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


def parse_case(value: str) -> BenchmarkCase:
    text = str(value or "").strip()
    provider, sep, model = text.partition(":")
    if not sep or not provider.strip() or not model.strip():
        raise argparse.ArgumentTypeError(
            f"invalid --case {value!r}; expected provider:model"
        )
    return BenchmarkCase(provider=provider.strip(), model=model.strip())


def default_cases() -> list[BenchmarkCase]:
    return [BenchmarkCase(provider=provider, model=model) for provider, model in DEFAULT_CASES]


def common_worker_command(
    case,
    *,
    script_path: Path,
    first_prompt: str,
    second_prompt: str,
    timezone_name: str,
    current_datetime: str,
    provider_home: str,
) -> list[str]:
    command = [
        sys.executable,
        str(script_path),
        "--worker",
        "--provider",
        case.provider,
        "--model",
        case.model,
        "--first-prompt",
        first_prompt,
        "--second-prompt",
        second_prompt,
        "--timezone",
        timezone_name,
        "--current-datetime",
        current_datetime,
    ]
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    if normalized_provider_home:
        command.extend(["--provider-home", normalized_provider_home])
    return command


def decode_worker_payload(stdout_text: str) -> dict:
    raw_text = str(stdout_text or "")
    decoder = json.JSONDecoder()
    candidates: list[str] = []
    if raw_text.strip():
        candidates.append(raw_text)
    lines = raw_text.splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("{", "[")):
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
        last_error = json.JSONDecodeError("decoded JSON payload is not an object", stripped, 0)
    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("expected JSON object output", raw_text, 0)
