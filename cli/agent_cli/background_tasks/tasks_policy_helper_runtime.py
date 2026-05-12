from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import tasks_facade_runtime
from .models import TaskEnvelope, TaskResult


POLICY_HELPER_REGRESSION_PROFILE = "policy_helper_regression"
POLICY_HELPER_REGRESSION_KIND = "policy_helper_live_cases"
POLICY_HELPER_REGRESSION_DEFAULT_COMBOS = ("glm_low_latency", "deepseek_low_latency")
POLICY_HELPER_REGRESSION_DEFAULT_ARGV = (
    "--profile",
    POLICY_HELPER_REGRESSION_PROFILE,
    "--provider",
    "glm",
    "--model",
    "glm_5",
    "--reasoning-effort",
    "high",
)
POLICY_HELPER_BACKGROUND_PROFILE_KEY = "policy_helper_background_profile"


def normalize_policy_helper_regression_envelope(envelope: TaskEnvelope) -> TaskEnvelope:
    payload = dict(envelope.payload or {})
    if not is_policy_helper_regression_payload(payload):
        return envelope
    user_argv = tasks_facade_runtime.normalize_argv(payload.get("argv"))
    normalized_payload = dict(payload)
    normalized_payload["kind"] = POLICY_HELPER_REGRESSION_KIND
    normalized_payload["argv"] = [*POLICY_HELPER_REGRESSION_DEFAULT_ARGV, *user_argv]
    normalized_payload[POLICY_HELPER_BACKGROUND_PROFILE_KEY] = POLICY_HELPER_REGRESSION_PROFILE
    normalized_payload.pop("preset", None)
    normalized_payload.pop("profile", None)
    if str(normalized_payload.get("suite") or "").strip().lower() == POLICY_HELPER_REGRESSION_PROFILE:
        normalized_payload.pop("suite", None)
    return TaskEnvelope.from_dict({**envelope.to_dict(), "payload": normalized_payload})


def is_policy_helper_regression_payload(payload: dict[str, Any]) -> bool:
    for key in ("preset", "profile", "kind", "suite"):
        value = str(payload.get(key) or "").strip().lower()
        if value == POLICY_HELPER_REGRESSION_PROFILE:
            return True
    return False


def enrich_policy_helper_smoke_result(result: TaskResult, *, envelope: TaskEnvelope) -> TaskResult:
    payload = dict(envelope.payload or {})
    artifact = dict(result.artifact or {})
    artifact_kind = str(artifact.get("kind") or payload.get("kind") or "").strip().lower()
    if artifact_kind != POLICY_HELPER_REGRESSION_KIND:
        return result
    profile = str(
        artifact.get("profile")
        or payload.get(POLICY_HELPER_BACKGROUND_PROFILE_KEY)
        or payload.get("profile")
        or payload.get("preset")
        or ""
    ).strip()
    report_payload = load_report_payload(artifact)
    if report_payload:
        report_profile = str(report_payload.get("profile") or "").strip()
        if report_profile:
            profile = report_profile
    combo_ids = policy_helper_combo_ids(report_payload)
    if not combo_ids:
        combo_ids = extract_option_values(tasks_facade_runtime.normalize_argv(payload.get("argv")), "--helper-combo")
    if not combo_ids and profile == POLICY_HELPER_REGRESSION_PROFILE:
        combo_ids = [*POLICY_HELPER_REGRESSION_DEFAULT_COMBOS]
    policy_helper_override = report_payload.get("policy_helper_override")
    if profile:
        artifact["profile"] = profile
        artifact["policy_helper_profile"] = profile
    artifact["policy_helper_helper_combo_ids"] = combo_ids
    artifact["policy_helper_helper_combo_count"] = len(combo_ids)
    if isinstance(policy_helper_override, dict):
        artifact["policy_helper_override"] = dict(policy_helper_override)
    summary_suffix = policy_helper_summary_suffix(
        profile=profile,
        combo_ids=combo_ids,
        policy_helper_override=policy_helper_override if isinstance(policy_helper_override, dict) else {},
    )
    if summary_suffix and summary_suffix not in str(result.summary or ""):
        result.summary = f"{result.summary} ({summary_suffix})".strip()
    result.artifact = artifact
    return result


def load_report_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    report_path = Path(str(artifact.get("report_path") or "")).expanduser()
    if not str(report_path).strip() or not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def policy_helper_combo_ids(report_payload: dict[str, Any]) -> list[str]:
    combos: list[str] = []
    helper_combos = report_payload.get("helper_combos")
    if isinstance(helper_combos, list):
        for item in helper_combos:
            if not isinstance(item, dict):
                continue
            combo_id = str(item.get("combo_id") or "").strip()
            if combo_id:
                combos.append(combo_id)
    helper_combo = report_payload.get("helper_combo")
    if isinstance(helper_combo, dict):
        combo_id = str(helper_combo.get("combo_id") or "").strip()
        if combo_id:
            combos.append(combo_id)
    if not combos:
        matrix_summary = report_payload.get("matrix_summary")
        if isinstance(matrix_summary, dict):
            combos.extend(str(key or "").strip() for key in matrix_summary.keys())
    return tasks_facade_runtime.dedupe_compact_items(combos)


def extract_option_values(argv: list[str], option_name: str) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(list(argv or [])):
        if token != option_name:
            continue
        if index + 1 >= len(argv):
            continue
        value = str(argv[index + 1] or "").strip()
        if value:
            values.append(value)
    return tasks_facade_runtime.dedupe_compact_items(values)


def policy_helper_summary_suffix(
    *,
    profile: str,
    combo_ids: list[str],
    policy_helper_override: dict[str, Any],
) -> str:
    fragments: list[str] = []
    if profile:
        fragments.append(f"profile={profile}")
    if combo_ids:
        fragments.append(f"helper_combos={','.join(combo_ids)}")
    provider = str(policy_helper_override.get("provider") or "").strip()
    model = str(policy_helper_override.get("model") or "").strip()
    if provider or model:
        fragments.append(f"helper_override={provider or '-'}:{model or '-'}")
    return ", ".join(fragments)
