from __future__ import annotations

import shlex
from typing import Any

from cli.agent_cli.slash_surface import normalize_command_text

_VALUE_FLAGS = {
    "--draft",
    "--filename",
    "--ext",
    "--limit",
    "--offset",
    "--path",
    "--server",
    "--server-name",
    "--uri",
    "--projected-name",
    "--arguments-json",
    "--token",
    "--headers-json",
    "--callback-json",
    "--request-id",
    "--approved",
    "--dir-path",
    "--file-path",
    "--pattern",
    "--include",
    "--mode",
    "--model",
    "--indentation",
    "--text",
    "--toolbar",
    "--duration",
    "--interval",
    "--output-dir",
    "--library-root",
    "--doc-id",
    "--max-chars",
    "--domains",
    "--domain",
    "--recency-days",
    "--market",
    "--line",
    "--depth",
    "--status",
    "--scope",
    "--note",
    "--approval-policy",
    "--sandbox-mode",
    "--web-search-mode",
    "--network-access",
    "--reasoning-effort",
    "--provider",
    "--base-url",
    "--api-key",
    "--write",
    "--repo",
    "--title",
    "--body",
    "--issue-number",
    "--labels",
    "--workflow-id",
    "--ref",
    "--inputs-json",
    "--token-env",
    "--api-base-url",
    "--correlation-id",
    "--approval-id",
    "--decided-by",
    "--decision-note",
    "--token-ref",
    "--auth-code",
    "--state",
    "--redirect-uri",
    "--callback-timeout-seconds",
    "--daemon",
    "--interval-seconds",
    "--refresh-window-seconds",
    "--wellknown-ttl",
    "--reason",
    "--timeout",
    "--cmd",
    "--workdir",
    "--shell",
    "--login",
    "--yield-time-ms",
    "--timeout-ms",
    "--wait-required",
    "--max-output-tokens",
    "--sandbox-permissions",
    "--justification",
    "--prefix-rule",
    "--additional-permissions-json",
    "--type",
    "--output-mode",
    "--after",
    "--after-context",
    "--before",
    "--before-context",
    "--context",
    "--blocked-domains",
    "--max-passes",
    "--dispatch-ready",
}
_BOOLEAN_FLAGS = {
    "--persist",
    "--confirm",
    "--debug",
    "--probe",
    "--replace",
    "--refresh",
    "--yes",
    "--clear",
    "--async",
    "--interrupt",
    "--double-click",
    "--fallback-click",
    "--no-recursive",
    "--no-front",
    "--fully-visible",
    "--center",
    "--tty",
    "--from-last-turn",
    "--auto",
    "--poll",
    "--wait-callback",
    "--listen",
    "--managed",
    "--force",
    "--line-numbers",
    "--line-number",
    "--case-insensitive",
    "--ignore-case",
    "--multiline",
    "--no-resume",
    "--resume-only",
}


def split_command(text: str) -> tuple[str, str]:
    normalized_text = normalize_command_text(text)
    body = str(
        normalized_text if str(normalized_text or "").lstrip().startswith("/") else text or ""
    ).lstrip()
    raw = body[1:].strip() if body.startswith("/") else body.strip()
    if not raw:
        return "help", ""
    if " " not in raw:
        return raw.lower(), ""
    name, arg_text = raw.split(" ", 1)
    return name.lower(), arg_text.strip()


def parse_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
    if not arg_text:
        return [], {}
    tokens = shlex.split(arg_text, posix=True)
    positionals: list[str] = []
    options: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _VALUE_FLAGS:
            if index + 1 >= len(tokens):
                break
            options[token[2:]] = tokens[index + 1]
            index += 2
            continue
        if token in _BOOLEAN_FLAGS:
            options[token[2:]] = True
            index += 1
            continue
        positionals.append(token)
        index += 1
    return positionals, options
