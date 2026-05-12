from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from typing import Callable, Sequence, TextIO

_SUBCOMMAND_MODULES: dict[str, str] = {
    "mcp": "cli.agent_cli.subcommands.mcp",
    "plugin": "cli.agent_cli.subcommands.plugin",
}
_ENTRYPOINT_CANDIDATES: tuple[str, ...] = (
    "main",
    "run",
    "dispatch_subcommand",
    "dispatch",
)


def _resolve_entrypoint(module: ModuleType, *, module_path: str) -> Callable[..., int]:
    for name in _ENTRYPOINT_CANDIDATES:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    raise RuntimeError(
        f"subcommand module '{module_path}' does not expose any supported entrypoint: "
        + ", ".join(_ENTRYPOINT_CANDIDATES)
    )


def _load_subcommand_entrypoint(command_name: str) -> Callable[..., int] | None:
    module_path = _SUBCOMMAND_MODULES[command_name]
    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", "") == module_path:
            return None
        raise
    return _resolve_entrypoint(module, module_path=module_path)


def dispatch_subcommand(
    argv: Sequence[str] | None,
    *,
    runtime=None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int | None:
    if argv is None:
        return None
    raw_argv = [str(item) for item in list(argv)]
    if not raw_argv:
        return None

    command_name = str(raw_argv[0] or "").strip().lower()
    if command_name not in _SUBCOMMAND_MODULES:
        return None

    entrypoint = _load_subcommand_entrypoint(command_name)
    if entrypoint is None:
        print(
            f"cli error: subcommand '{command_name}' is not available in this build",
            file=stderr or sys.stderr,
        )
        return 1

    exit_code = entrypoint(
        raw_argv[1:],
        runtime=runtime,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )
    if exit_code is None:
        return 0
    return int(exit_code)


__all__ = ["dispatch_subcommand"]
