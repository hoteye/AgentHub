from __future__ import annotations

import json
import shlex
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_paths import (
    LEGACY_PROJECT_LOCAL_DATA_DIRNAMES,
    PROJECT_LOCAL_DATA_DIRNAME,
    runtime_project_root,
)
from cli.agent_cli.workspace_context import find_project_root, project_root_markers


RUNTIME_EXEC_POLICY_RULES_FILENAME = "exec_policy_rules.jsonl"
RUNTIME_EXEC_POLICY_RULE_SCHEMA_VERSION = 1
RUNTIME_EXEC_POLICY_RULE_KIND = "exec_policy_rule"

_DECISION_ALIASES = {
    "allow": "allow",
    "allowed": "allow",
    "ask": "prompt",
    "deny": "forbidden",
    "denied": "forbidden",
    "forbid": "forbidden",
    "forbidden": "forbidden",
    "prompt": "prompt",
}
_MATCH_KIND_ALIASES = {
    "exact": "exact",
    "full": "exact",
    "prefix": "prefix",
    "startswith": "prefix",
    "token_prefix": "prefix",
}
_DEFAULT_SCOPE = "workspace"
_DEFAULT_SOURCE = "user"
_WRITE_LOCK = threading.Lock()


def _safe_resolve(path: str | Path | None) -> Path:
    candidate = Path(path or ".").expanduser()
    try:
        return candidate.resolve()
    except OSError:
        return candidate


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _command_tokens_from_text(value: object) -> tuple[str, ...]:
    normalized = _normalized_text(value)
    if not normalized:
        return ()
    try:
        tokens = tuple(str(token).strip() for token in shlex.split(normalized, posix=True) if str(token).strip())
    except ValueError:
        tokens = ()
    if tokens:
        return tokens
    return (normalized,)


def _command_tokens_from_value(value: object) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        tokens = tuple(_normalized_text(token) for token in value if _normalized_text(token))
        if tokens:
            return tokens
    return _command_tokens_from_text(value)


def _join_command_tokens(tokens: Sequence[str]) -> str:
    if hasattr(shlex, "join"):
        return shlex.join(list(tokens))
    return " ".join(shlex.quote(token) for token in tokens)


def _normalized_decision(value: object) -> str:
    token = _normalized_text(value).lower()
    normalized = _DECISION_ALIASES.get(token)
    if normalized is None:
        raise ValueError(f"unsupported exec policy decision: {value!r}")
    return normalized


def _normalized_match_kind(value: object) -> str:
    token = _normalized_text(value).lower() or "prefix"
    normalized = _MATCH_KIND_ALIASES.get(token)
    if normalized is None:
        raise ValueError(f"unsupported exec policy match kind: {value!r}")
    return normalized


def _json_safe(value: object) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        items = [_json_safe(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _normalized_source_metadata(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _json_safe(item) for key, item in value.items()}


def _resolved_project_root(
    *,
    cwd: str | Path | None = None,
    root: str | Path | None = None,
) -> Path:
    if root is not None and _normalized_text(root):
        return _safe_resolve(root)
    if cwd is not None and _normalized_text(cwd):
        resolved_cwd = _safe_resolve(cwd)
        try:
            markers = project_root_markers(resolved_cwd)
            return _safe_resolve(find_project_root(resolved_cwd, markers))
        except Exception:
            return resolved_cwd
    return runtime_project_root()


def _rule_identity(*, scope: str, match_kind: str, normalized_command: str) -> str:
    return f"{scope}:{match_kind}:{normalized_command}"


@dataclass(slots=True)
class RuntimeExecPolicyRule:
    decision: str
    match_kind: str
    command_tokens: tuple[str, ...]
    normalized_command: str
    program_name: str
    program_basename: str
    scope: str = _DEFAULT_SCOPE
    justification: str = ""
    source: str = _DEFAULT_SOURCE
    source_metadata: dict[str, Any] = field(default_factory=dict)
    rule_id: str = ""

    @property
    def identity(self) -> str:
        return _rule_identity(
            scope=self.scope,
            match_kind=self.match_kind,
            normalized_command=self.normalized_command,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RUNTIME_EXEC_POLICY_RULE_SCHEMA_VERSION,
            "kind": RUNTIME_EXEC_POLICY_RULE_KIND,
            "rule_id": self.rule_id or self.identity,
            "decision": self.decision,
            "match_kind": self.match_kind,
            "scope": self.scope,
            "command_tokens": list(self.command_tokens),
            "normalized_command": self.normalized_command,
            "program_name": self.program_name,
            "program_basename": self.program_basename,
            "justification": self.justification,
            "source": self.source,
            "source_metadata": _json_safe(self.source_metadata),
        }


def normalize_exec_policy_rule(rule: Mapping[str, object] | RuntimeExecPolicyRule) -> RuntimeExecPolicyRule:
    payload = rule.to_dict() if isinstance(rule, RuntimeExecPolicyRule) else dict(rule or {})
    decision = _normalized_decision(payload.get("decision"))
    match_kind = _normalized_match_kind(payload.get("match_kind"))
    command_tokens = _command_tokens_from_value(payload.get("command_tokens"))
    if not command_tokens:
        command_tokens = _command_tokens_from_value(
            payload.get("normalized_command")
            or payload.get("command")
            or payload.get("command_pattern")
            or payload.get("pattern")
        )
    if not command_tokens:
        raise ValueError("exec policy rule requires a command or command_tokens")

    normalized_command = _join_command_tokens(command_tokens)
    program_name = command_tokens[0]
    program_basename = Path(program_name).name or program_name
    scope = _normalized_text(payload.get("scope")) or _DEFAULT_SCOPE
    justification = _normalized_text(payload.get("justification"))
    source = _normalized_text(payload.get("source")) or _DEFAULT_SOURCE
    source_metadata = _normalized_source_metadata(
        payload.get("source_metadata")
        if payload.get("source_metadata") is not None
        else payload.get("metadata")
    )
    rule_id = _normalized_text(payload.get("rule_id")) or _rule_identity(
        scope=scope,
        match_kind=match_kind,
        normalized_command=normalized_command,
    )
    return RuntimeExecPolicyRule(
        decision=decision,
        match_kind=match_kind,
        command_tokens=command_tokens,
        normalized_command=normalized_command,
        program_name=program_name,
        program_basename=program_basename,
        scope=scope,
        justification=justification,
        source=source,
        source_metadata=source_metadata,
        rule_id=rule_id,
    )


def resolve_runtime_exec_policy_rules_path(
    *,
    cwd: str | Path | None = None,
    root: str | Path | None = None,
) -> Path:
    project_root = _resolved_project_root(cwd=cwd, root=root)
    return project_root / PROJECT_LOCAL_DATA_DIRNAME / RUNTIME_EXEC_POLICY_RULES_FILENAME


def resolve_runtime_exec_policy_rules_load_paths(
    *,
    cwd: str | Path | None = None,
    root: str | Path | None = None,
) -> list[Path]:
    project_root = _resolved_project_root(cwd=cwd, root=root)
    preferred = project_root / PROJECT_LOCAL_DATA_DIRNAME / RUNTIME_EXEC_POLICY_RULES_FILENAME
    candidates = [
        project_root / dirname / RUNTIME_EXEC_POLICY_RULES_FILENAME
        for dirname in LEGACY_PROJECT_LOCAL_DATA_DIRNAMES
    ]
    candidates = [candidate for candidate in candidates if candidate.exists()]
    candidates.append(preferred)
    seen: set[Path] = set()
    resolved: list[Path] = []
    for candidate in candidates:
        path = _safe_resolve(candidate)
        if path in seen:
            continue
        seen.add(path)
        resolved.append(path)
    return resolved


def merge_runtime_exec_policy_rules(
    *rule_sets: Iterable[Mapping[str, object] | RuntimeExecPolicyRule],
) -> list[RuntimeExecPolicyRule]:
    merged: dict[str, RuntimeExecPolicyRule] = {}
    for rule_set in rule_sets:
        for raw_rule in rule_set:
            rule = normalize_exec_policy_rule(raw_rule)
            identity = rule.identity
            if identity in merged:
                del merged[identity]
            merged[identity] = rule
    return list(merged.values())


def match_runtime_exec_policy_rule(
    command: str | Sequence[str],
    *,
    rules: Iterable[Mapping[str, object] | RuntimeExecPolicyRule] | None = None,
    cwd: str | Path | None = None,
    root: str | Path | None = None,
) -> RuntimeExecPolicyRule | None:
    command_tokens = _command_tokens_from_value(command)
    if not command_tokens:
        return None
    normalized_command = _join_command_tokens(command_tokens)
    loaded_rules = (
        [normalize_exec_policy_rule(rule) for rule in rules]
        if rules is not None
        else load_runtime_exec_policy_rules(cwd=cwd, root=root)
    )
    best_match: tuple[int, int, int, RuntimeExecPolicyRule] | None = None
    for index, rule in enumerate(loaded_rules):
        if rule.match_kind == "exact":
            if rule.normalized_command != normalized_command:
                continue
            score = (2, len(rule.command_tokens), index)
        elif tuple(command_tokens[: len(rule.command_tokens)]) == tuple(rule.command_tokens):
            score = (1, len(rule.command_tokens), index)
        else:
            continue
        if best_match is None or score > best_match[:3]:
            best_match = (score[0], score[1], score[2], rule)
    return best_match[3] if best_match is not None else None


def load_runtime_exec_policy_rules(
    *,
    path: str | Path | None = None,
    cwd: str | Path | None = None,
    root: str | Path | None = None,
) -> list[RuntimeExecPolicyRule]:
    if path is not None and _normalized_text(path):
        targets = [_safe_resolve(path)]
    else:
        targets = resolve_runtime_exec_policy_rules_load_paths(cwd=cwd, root=root)

    loaded: list[RuntimeExecPolicyRule] = []
    for target in targets:
        try:
            exists = target.exists()
        except OSError:
            exists = False
        if not exists:
            continue
        try:
            with target.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, Mapping):
                        continue
                    try:
                        loaded.append(normalize_exec_policy_rule(payload))
                    except ValueError:
                        continue
        except OSError:
            continue
    return merge_runtime_exec_policy_rules(loaded)


def append_runtime_exec_policy_rule(
    rule: Mapping[str, object] | RuntimeExecPolicyRule,
    *,
    path: str | Path | None = None,
    cwd: str | Path | None = None,
    root: str | Path | None = None,
) -> RuntimeExecPolicyRule:
    normalized = normalize_exec_policy_rule(rule)
    target = _safe_resolve(path) if path is not None and _normalized_text(path) else resolve_runtime_exec_policy_rules_path(cwd=cwd, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = normalized.to_dict()
    with _WRITE_LOCK:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return normalized


__all__ = [
    "RUNTIME_EXEC_POLICY_RULES_FILENAME",
    "RUNTIME_EXEC_POLICY_RULE_KIND",
    "RUNTIME_EXEC_POLICY_RULE_SCHEMA_VERSION",
    "RuntimeExecPolicyRule",
    "append_runtime_exec_policy_rule",
    "load_runtime_exec_policy_rules",
    "match_runtime_exec_policy_rule",
    "merge_runtime_exec_policy_rules",
    "normalize_exec_policy_rule",
    "resolve_runtime_exec_policy_rules_load_paths",
    "resolve_runtime_exec_policy_rules_path",
]
