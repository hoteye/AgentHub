from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    name: str
    prefixes: tuple[str, ...]
    commands: tuple[str, ...]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULES_CONFIG_PATH = PROJECT_ROOT / "scripts" / "governance" / "change_test_gate_rules.yaml"


def _as_non_empty_str(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _as_str_list(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    items: list[str] = []
    for index, item in enumerate(value):
        items.append(_as_non_empty_str(item, field=f"{field}[{index}]"))
    if not items:
        raise ValueError(f"{field} must not be empty")
    return tuple(items)


def _parse_rules_payload(payload: object) -> tuple[Rule, ...]:
    if not isinstance(payload, dict):
        raise ValueError("rules config must be an object with a top-level 'rules' key")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError("rules config must include a 'rules' list")
    rules: list[Rule] = []
    seen_names: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"rules[{index}] must be an object")
        name = _as_non_empty_str(raw_rule.get("name"), field=f"rules[{index}].name")
        if name in seen_names:
            raise ValueError(f"duplicate rule name: {name}")
        seen_names.add(name)
        prefixes = _as_str_list(raw_rule.get("prefixes"), field=f"rules[{index}].prefixes")
        commands = _as_str_list(raw_rule.get("commands"), field=f"rules[{index}].commands")
        rules.append(Rule(name=name, prefixes=prefixes, commands=commands))
    if not rules:
        raise ValueError("rules config must define at least one rule")
    return tuple(rules)


def load_rules(config_path: Path | None = None) -> tuple[Rule, ...]:
    path = config_path or RULES_CONFIG_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read rules config: {path}: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON-compatible YAML in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return _parse_rules_payload(payload)


RULES: tuple[Rule, ...] = load_rules(RULES_CONFIG_PATH)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run required minimal tests based on changed file paths."
    )
    parser.add_argument(
        "--working-dir",
        default="cli",
        help="Directory where pytest commands should run.",
    )
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("GITHUB_BASE_REF", ""),
        help="GitHub PR base ref (e.g. main). Optional.",
    )
    parser.add_argument(
        "--changed",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Explicit changed path (repeatable). "
            "If provided, git diff discovery is skipped."
        ),
    )
    parser.add_argument(
        "--rules-file",
        default=str(RULES_CONFIG_PATH),
        help="Path to JSON-compatible YAML rules config file.",
    )
    return parser.parse_args()


def run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def diff_base(base_ref: str) -> str:
    if base_ref:
        remote_ref = f"origin/{base_ref}"
        subprocess.run(["git", "fetch", "--no-tags", "origin", base_ref], check=False)
        try:
            return run_git(["merge-base", "HEAD", remote_ref])
        except subprocess.CalledProcessError:
            pass
    try:
        return run_git(["rev-parse", "HEAD~1"])
    except subprocess.CalledProcessError:
        return run_git(["rev-parse", "HEAD"])


def changed_files(base_ref: str, explicit_paths: list[str] | None = None) -> list[str]:
    if explicit_paths:
        deduped: list[str] = []
        seen: set[str] = set()
        for path in explicit_paths:
            normalized = path.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped
    base = diff_base(base_ref)
    output = run_git(["diff", "--name-only", f"{base}...HEAD"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def matches(path: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix or path.startswith(prefix)


def matched_rules(paths: list[str], rules: tuple[Rule, ...] | None = None) -> list[tuple[Rule, list[str]]]:
    active_rules = rules if rules is not None else RULES
    selected: list[tuple[Rule, list[str]]] = []
    for rule in active_rules:
        matched_paths = [
            path
            for path in paths
            if any(matches(path, prefix) for prefix in rule.prefixes)
        ]
        if matched_paths:
            selected.append((rule, matched_paths))
    return selected


def required_commands(paths: list[str], rules: tuple[Rule, ...] | None = None) -> list[str]:
    selected: list[str] = []
    for rule, _matched_paths in matched_rules(paths, rules=rules):
        for cmd in rule.commands:
            if cmd not in selected:
                selected.append(cmd)
    return selected


def run_commands(commands: list[str], working_dir: Path) -> int:
    for command in commands:
        print(f"[test-gate] run: {command}")
        completed = subprocess.run(
            shlex.split(command),
            cwd=working_dir,
            check=False,
        )
        if completed.returncode == 5:
            print(
                "[test-gate] no tests collected for this selector (exit 5); treated as neutral"
            )
            continue
        if completed.returncode != 0:
            print(f"[test-gate] failed: {command}")
            return completed.returncode
    return 0


def main() -> int:
    args = parse_args()
    rules_file = Path(getattr(args, "rules_file", str(RULES_CONFIG_PATH)))
    try:
        active_rules = load_rules(rules_file)
    except ValueError as exc:
        print(f"[test-gate] config error: {exc}")
        return 2
    explicit_paths = getattr(args, "changed", None)
    if explicit_paths:
        paths = changed_files(args.base_ref, explicit_paths=explicit_paths)
    else:
        paths = changed_files(args.base_ref)
    rule_hits = matched_rules(paths, rules=active_rules)
    commands = required_commands(paths, rules=active_rules)

    if not commands:
        print("[test-gate] no mapped paths changed; skip")
        return 0

    print("[test-gate] changed file count:", len(paths))
    print("[test-gate] matched rule count:", len(rule_hits))
    for rule, matched_paths in rule_hits:
        sample = ", ".join(matched_paths[:2])
        if len(matched_paths) > 2:
            sample = f"{sample}, ..."
        print(f"[test-gate] matched rule: {rule.name} <- {sample}")
    print("[test-gate] selected command count:", len(commands))
    return run_commands(commands, working_dir=Path(args.working_dir))


if __name__ == "__main__":
    sys.exit(main())
