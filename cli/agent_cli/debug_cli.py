from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

DEBUG_TEXT_LOG_ENV_KEY = "AGENTHUB_DEBUG_TEXT_LOG"
DEBUG_FILTER_ENV_KEY = "AGENTHUB_DEBUG_FILTER"
DEBUG_LOG_DIR_ENV_KEY = "AGENTHUB_DEBUG_LOG_DIR"
START_DEBUG_LOG_ENV_KEY = "AGENTHUB_START_DEBUG_LOG"


def _coerce_text(value: Any) -> str:
    return str(value or "").strip()


def _default_sidecar_log_dir(debug_file: str) -> str:
    path = Path(debug_file).expanduser()
    return str(Path(f"{path}.d"))


def _scan_optional_value(argv: list[str], index: int) -> tuple[str | None, int]:
    next_index = index + 1
    if next_index >= len(argv):
        return None, index
    candidate = _coerce_text(argv[next_index])
    if not candidate:
        return None, index
    if candidate.startswith('-') and not candidate.startswith('!'):
        return None, index
    return candidate, next_index


def scan_debug_cli_args(argv: Sequence[str] | None) -> dict[str, Any]:
    args = [str(item or "") for item in list(argv or [])]
    enabled = False
    debug_filter: str | None = None
    debug_file: str | None = None
    index = 0
    while index < len(args):
        token = args[index]
        if token == '--debug-file':
            enabled = True
            if index + 1 < len(args):
                debug_file = _coerce_text(args[index + 1]) or debug_file
                index += 2
                continue
        elif token.startswith('--debug-file='):
            enabled = True
            debug_file = _coerce_text(token.split('=', 1)[1]) or debug_file
            index += 1
            continue
        elif token == '--debug':
            enabled = True
            value, consumed_index = _scan_optional_value(args, index)
            if value is not None:
                debug_filter = value
                index = consumed_index + 1
                continue
        elif token.startswith('--debug='):
            enabled = True
            debug_filter = _coerce_text(token.split('=', 1)[1]) or debug_filter
            index += 1
            continue
        elif token == '-d':
            enabled = True
            value, consumed_index = _scan_optional_value(args, index)
            if value is not None:
                debug_filter = value
                index = consumed_index + 1
                continue
        elif token.startswith('-d') and len(token) > 2:
            enabled = True
            debug_filter = _coerce_text(token[2:]) or debug_filter
            index += 1
            continue
        index += 1
    return {
        'enabled': enabled or bool(debug_file),
        'debug_filter': debug_filter,
        'debug_file': debug_file,
    }


def apply_debug_settings(
    *,
    enabled: bool,
    debug_filter: str | None,
    debug_file: str | None,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    env = environ if environ is not None else os.environ
    normalized_filter = _coerce_text(debug_filter)
    normalized_file = _coerce_text(debug_file)
    if not enabled and not normalized_file and not normalized_filter:
        return
    text_target = normalized_file or 'stderr'
    env[DEBUG_TEXT_LOG_ENV_KEY] = text_target
    env[START_DEBUG_LOG_ENV_KEY] = text_target
    if normalized_filter and normalized_filter != '*':
        env[DEBUG_FILTER_ENV_KEY] = normalized_filter
    elif enabled:
        env.pop(DEBUG_FILTER_ENV_KEY, None)
    if normalized_file and not _coerce_text(env.get(DEBUG_LOG_DIR_ENV_KEY)):
        env[DEBUG_LOG_DIR_ENV_KEY] = _default_sidecar_log_dir(normalized_file)


def preconfigure_debug_from_argv(
    argv: Sequence[str] | None,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> dict[str, Any]:
    scanned = scan_debug_cli_args(argv)
    apply_debug_settings(
        enabled=bool(scanned.get('enabled')),
        debug_filter=scanned.get('debug_filter'),
        debug_file=scanned.get('debug_file'),
        environ=environ,
    )
    return scanned


def configure_debug_from_args(
    args: Any,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    apply_debug_settings(
        enabled=bool(_coerce_text(getattr(args, 'debug', None)) or getattr(args, 'debug', None) is not None or _coerce_text(getattr(args, 'debug_file', None))),
        debug_filter=_coerce_text(getattr(args, 'debug', None)) or None,
        debug_file=_coerce_text(getattr(args, 'debug_file', None)) or None,
        environ=environ,
    )


def debug_settings_from_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    env = environ if environ is not None else os.environ
    return {
        'text_log': _coerce_text(env.get(DEBUG_TEXT_LOG_ENV_KEY)),
        'filter': _coerce_text(env.get(DEBUG_FILTER_ENV_KEY)),
        'log_dir': _coerce_text(env.get(DEBUG_LOG_DIR_ENV_KEY)),
        'startup_log': _coerce_text(env.get(START_DEBUG_LOG_ENV_KEY)),
    }
