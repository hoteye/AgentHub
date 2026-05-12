from __future__ import annotations

from typing import Any, Iterable

from .benchmark_acceptance_case_helpers import (
    PASS_LEVEL_ORDER,
    _benchmark_case_order,
    _evidence_pass_level,
    _sorted_rows,
    get_benchmark_case_spec,
    row_contract_failures,
)


SCORING_MODEL_ID = "native_interaction_parity_v1"
SCORING_COMPONENT_MAX_SCORES = {
    "tool_name_correct": 35.0,
    "arguments_correct": 20.0,
    "result_usable": 25.0,
    "time_to_first_event_ms": 10.0,
    "time_to_first_tool_ms": 10.0,
}
LATENCY_SCORING_WINDOWS_MS = {
    "time_to_first_event_ms": (250, 2000),
    "time_to_first_tool_ms": (1000, 5000),
}
EVIDENCE_LEVEL_SCORE_WEIGHTS = {
    "synthetic": 0.7,
    "fixture_live": 0.85,
    "operator_live": 1.0,
}


def _round_score(value: float) -> float:
    return round(float(value), 4)


def _latency_score(field: str, value: Any) -> float:
    max_score = SCORING_COMPONENT_MAX_SCORES[field]
    if not isinstance(value, int) or value < 0:
        return 0.0
    target_ms, zero_score_ms = LATENCY_SCORING_WINDOWS_MS[field]
    if value <= target_ms:
        return max_score
    if value >= zero_score_ms:
        return 0.0
    remaining = zero_score_ms - value
    window = zero_score_ms - target_ms
    return _round_score(max_score * (remaining / window))


def _average_score(values: Iterable[float]) -> float:
    items = [float(item) for item in list(values or [])]
    if not items:
        return 0.0
    return _round_score(sum(items) / len(items))


def _normalized_unique_strings(values: Iterable[str] | None) -> list[str]:
    normalized = {str(item or "").strip() for item in list(values or []) if str(item or "").strip()}
    return sorted(normalized, key=lambda item: (_benchmark_case_order(item), item))


def _component_score_summary(row_scores: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized_scores = [dict(item or {}) for item in list(row_scores or []) if isinstance(item, dict)]
    summary: dict[str, dict[str, Any]] = {}
    for field, max_score in SCORING_COMPONENT_MAX_SCORES.items():
        average_component_score = _average_score(
            item.get("component_scores", {}).get(field, {}).get("score", 0.0)
            for item in normalized_scores
        )
        summary[field] = {
            "score": average_component_score,
            "max_score": max_score,
            "score_ratio": _round_score(average_component_score / max_score) if max_score else 0.0,
        }
    return summary


def _evidence_pass_level_floor(rows: Iterable[dict[str, Any]]) -> str:
    evidence_pass_level = ""
    for item in [dict(candidate or {}) for candidate in list(rows or []) if isinstance(candidate, dict)]:
        level = _evidence_pass_level(str(item.get("evidence_level") or "").strip())
        if not level:
            return ""
        if not evidence_pass_level or PASS_LEVEL_ORDER[level] < PASS_LEVEL_ORDER[evidence_pass_level]:
            evidence_pass_level = level
    return evidence_pass_level


def _expected_case_ids_by_surface(expected_case_ids: Iterable[str] | None) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for case_id in _normalized_unique_strings(expected_case_ids):
        try:
            spec = get_benchmark_case_spec(case_id)
        except KeyError:
            continue
        grouped.setdefault(spec.surface, []).append(spec.case_id)
    return {surface: _normalized_unique_strings(case_ids) for surface, case_ids in grouped.items()}


def score_acceptance_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row or {})
    contract_failures = row_contract_failures(normalized)
    component_scores = {
        "tool_name_correct": {
            "score": SCORING_COMPONENT_MAX_SCORES["tool_name_correct"] if normalized.get("tool_name_correct") is True else 0.0,
            "max_score": SCORING_COMPONENT_MAX_SCORES["tool_name_correct"],
            "value": normalized.get("tool_name_correct"),
        },
        "arguments_correct": {
            "score": SCORING_COMPONENT_MAX_SCORES["arguments_correct"] if normalized.get("arguments_correct") is True else 0.0,
            "max_score": SCORING_COMPONENT_MAX_SCORES["arguments_correct"],
            "value": normalized.get("arguments_correct"),
        },
        "result_usable": {
            "score": SCORING_COMPONENT_MAX_SCORES["result_usable"] if normalized.get("result_usable") is True else 0.0,
            "max_score": SCORING_COMPONENT_MAX_SCORES["result_usable"],
            "value": normalized.get("result_usable"),
        },
        "time_to_first_event_ms": {
            "score": _latency_score("time_to_first_event_ms", normalized.get("time_to_first_event_ms")),
            "max_score": SCORING_COMPONENT_MAX_SCORES["time_to_first_event_ms"],
            "value": normalized.get("time_to_first_event_ms"),
            "target_ms": LATENCY_SCORING_WINDOWS_MS["time_to_first_event_ms"][0],
            "zero_score_ms": LATENCY_SCORING_WINDOWS_MS["time_to_first_event_ms"][1],
        },
        "time_to_first_tool_ms": {
            "score": _latency_score("time_to_first_tool_ms", normalized.get("time_to_first_tool_ms")),
            "max_score": SCORING_COMPONENT_MAX_SCORES["time_to_first_tool_ms"],
            "value": normalized.get("time_to_first_tool_ms"),
            "target_ms": LATENCY_SCORING_WINDOWS_MS["time_to_first_tool_ms"][0],
            "zero_score_ms": LATENCY_SCORING_WINDOWS_MS["time_to_first_tool_ms"][1],
        },
    }
    parity_max_score = _round_score(sum(component["max_score"] for component in component_scores.values()))
    parity_score = _round_score(sum(component["score"] for component in component_scores.values()))
    evidence_level = str(normalized.get("evidence_level") or "").strip()
    confidence_weight = _round_score(EVIDENCE_LEVEL_SCORE_WEIGHTS.get(evidence_level, 0.0))
    native_parity_score = _round_score(parity_score * confidence_weight)
    return {
        "case_id": str(normalized.get("case_id") or "").strip(),
        "surface": str(normalized.get("surface") or "").strip(),
        "evidence_level": evidence_level,
        "evidence_pass_level": str(normalized.get("evidence_pass_level") or "").strip(),
        "acceptance_passed": normalized.get("acceptance_passed") is True,
        "contract_failures": contract_failures,
        "contract_failure_count": len(contract_failures),
        "confidence_weight": confidence_weight,
        "parity_score": parity_score,
        "parity_max_score": parity_max_score,
        "parity_score_ratio": _round_score(parity_score / parity_max_score) if parity_max_score else 0.0,
        "native_parity_score": native_parity_score,
        "score": native_parity_score,
        "max_score": parity_max_score,
        "score_ratio": _round_score(native_parity_score / parity_max_score) if parity_max_score else 0.0,
        "component_scores": component_scores,
    }


def score_acceptance_rows(
    rows: Iterable[dict[str, Any]],
    *,
    expected_case_ids: Iterable[str] | None = None,
    required_surfaces: Iterable[str] | None = None,
) -> dict[str, Any]:
    normalized_rows = _sorted_rows(rows)
    row_scores = [score_acceptance_row(item) for item in normalized_rows]
    case_ids_expected = _normalized_unique_strings(expected_case_ids) or _normalized_unique_strings(
        item.get("case_id") for item in normalized_rows
    )
    required_surface_list = sorted(
        {str(item or "").strip() for item in list(required_surfaces or []) if str(item or "").strip()}
    ) or sorted({str(item.get("surface") or "").strip() for item in normalized_rows if str(item.get("surface") or "").strip()})
    case_ids_covered = _normalized_unique_strings(item.get("case_id") for item in normalized_rows)
    surfaces_covered = sorted({str(item.get("surface") or "").strip() for item in normalized_rows if str(item.get("surface") or "").strip()})
    missing_case_ids = [case_id for case_id in case_ids_expected if case_id not in case_ids_covered]
    missing_surfaces = [surface for surface in required_surface_list if surface not in surfaces_covered]
    case_coverage_ratio = _round_score(len(case_ids_covered) / len(case_ids_expected)) if case_ids_expected else 0.0
    surface_coverage_ratio = _round_score(len(surfaces_covered) / len(required_surface_list)) if required_surface_list else 0.0
    coverage_ratio = _average_score([case_coverage_ratio, surface_coverage_ratio]) if (case_ids_expected or required_surface_list) else 1.0
    parity_score = _average_score(item["parity_score"] for item in row_scores)
    average_row_native_parity_score = _average_score(item["native_parity_score"] for item in row_scores)
    native_parity_score = _round_score(average_row_native_parity_score * coverage_ratio)
    contract_valid_row_ratio = (
        _round_score(sum(1 for item in row_scores if item["contract_failure_count"] == 0) / len(row_scores))
        if row_scores
        else 0.0
    )
    accepted_row_ratio = (
        _round_score(sum(1 for item in row_scores if item["acceptance_passed"]) / len(row_scores))
        if row_scores
        else 0.0
    )
    evidence_weights = [item["confidence_weight"] for item in row_scores]
    evidence_weight_floor = min(evidence_weights) if evidence_weights else 0.0
    evidence_weight_average = _average_score(evidence_weights)
    evidence_levels_covered = sorted(
        {
            str(item.get("evidence_level") or "").strip()
            for item in normalized_rows
            if str(item.get("evidence_level") or "").strip()
        }
    )
    evidence_pass_level_floor = _evidence_pass_level_floor(normalized_rows)
    component_scores = _component_score_summary(row_scores)
    expected_case_ids_by_surface = _expected_case_ids_by_surface(case_ids_expected)

    surface_groups: dict[str, list[dict[str, Any]]] = {surface: [] for surface in required_surface_list}
    for item in row_scores:
        surface = str(item.get("surface") or "").strip()
        if not surface:
            continue
        surface_groups.setdefault(surface, []).append(item)

    surface_scores: list[dict[str, Any]] = []
    for surface in sorted(surface_groups):
        items = surface_groups[surface]
        expected_surface_case_ids = expected_case_ids_by_surface.get(surface) or _normalized_unique_strings(
            item.get("case_id") for item in items
        )
        covered_surface_case_ids = _normalized_unique_strings(item.get("case_id") for item in items)
        missing_surface_case_ids = [case_id for case_id in expected_surface_case_ids if case_id not in covered_surface_case_ids]
        surface_case_coverage_ratio = (
            _round_score(len(covered_surface_case_ids) / len(expected_surface_case_ids))
            if expected_surface_case_ids
            else (1.0 if items else 0.0)
        )
        average_surface_native_parity_score = _average_score(item.get("native_parity_score", 0.0) for item in items)
        average_surface_parity_score = _average_score(item.get("parity_score", 0.0) for item in items)
        surface_native_parity_score = _round_score(average_surface_native_parity_score * surface_case_coverage_ratio)
        surface_component_scores = _component_score_summary(items)
        surface_evidence_weights = [float(item.get("confidence_weight", 0.0) or 0.0) for item in items]
        surface_scores.append(
            {
                "surface": surface,
                "rows_scored": len(items),
                "case_ids_expected": expected_surface_case_ids,
                "case_ids_covered": covered_surface_case_ids,
                "missing_case_ids": missing_surface_case_ids,
                "case_coverage_ratio": surface_case_coverage_ratio,
                "acceptance_passed": bool(items) and not missing_surface_case_ids and all(
                    item.get("acceptance_passed") is True and item.get("contract_failure_count", 0) == 0
                    for item in items
                ),
                "accepted_row_ratio": (
                    _round_score(sum(1 for item in items if item.get("acceptance_passed") is True) / len(items))
                    if items
                    else 0.0
                ),
                "contract_valid_row_ratio": (
                    _round_score(sum(1 for item in items if item.get("contract_failure_count", 0) == 0) / len(items))
                    if items
                    else 0.0
                ),
                "native_parity_score": surface_native_parity_score,
                "score": surface_native_parity_score,
                "max_score": 100.0,
                "score_ratio": _round_score(surface_native_parity_score / 100.0),
                "parity_score": average_surface_parity_score,
                "parity_max_score": 100.0,
                "parity_score_ratio": _round_score(average_surface_parity_score / 100.0),
                "evidence_weight_average": _average_score(surface_evidence_weights),
                "evidence_weight_floor": _round_score(min(surface_evidence_weights) if surface_evidence_weights else 0.0),
                "evidence_pass_level_floor": _evidence_pass_level_floor(items),
                "component_scores": surface_component_scores,
            }
        )

    overall = {
        "native_parity_score": native_parity_score,
        "score": native_parity_score,
        "max_score": 100.0,
        "score_ratio": _round_score(native_parity_score / 100.0),
        "parity_score": parity_score,
        "parity_max_score": 100.0,
        "parity_score_ratio": _round_score(parity_score / 100.0),
        "coverage_ratio": coverage_ratio,
        "case_coverage_ratio": case_coverage_ratio,
        "surface_coverage_ratio": surface_coverage_ratio,
        "contract_valid_row_ratio": contract_valid_row_ratio,
        "accepted_row_ratio": accepted_row_ratio,
        "evidence_weight_average": evidence_weight_average,
        "evidence_weight_floor": _round_score(evidence_weight_floor),
        "evidence_pass_level_floor": evidence_pass_level_floor,
        "evidence_levels_covered": evidence_levels_covered,
        "expected_case_count": len(case_ids_expected),
        "rows_scored": len(row_scores),
        "surface_count": len(surface_scores),
        "case_ids_expected": case_ids_expected,
        "case_ids_covered": case_ids_covered,
        "missing_case_ids": missing_case_ids,
        "required_surfaces": required_surface_list,
        "surfaces_covered": surfaces_covered,
        "missing_surfaces": missing_surfaces,
        "component_scores": component_scores,
    }
    return {
        "model": SCORING_MODEL_ID,
        "score": overall["score"],
        "native_parity_score": overall["native_parity_score"],
        "max_score": overall["max_score"],
        "score_ratio": overall["score_ratio"],
        "parity_score": overall["parity_score"],
        "parity_max_score": overall["parity_max_score"],
        "parity_score_ratio": overall["parity_score_ratio"],
        "coverage_ratio": overall["coverage_ratio"],
        "case_coverage_ratio": overall["case_coverage_ratio"],
        "surface_coverage_ratio": overall["surface_coverage_ratio"],
        "contract_valid_row_ratio": overall["contract_valid_row_ratio"],
        "accepted_row_ratio": overall["accepted_row_ratio"],
        "evidence_weight_average": overall["evidence_weight_average"],
        "evidence_weight_floor": overall["evidence_weight_floor"],
        "evidence_pass_level_floor": overall["evidence_pass_level_floor"],
        "evidence_levels_covered": list(overall["evidence_levels_covered"]),
        "expected_case_count": overall["expected_case_count"],
        "rows_scored": overall["rows_scored"],
        "surface_count": overall["surface_count"],
        "case_ids_expected": list(overall["case_ids_expected"]),
        "case_ids_covered": list(overall["case_ids_covered"]),
        "missing_case_ids": list(overall["missing_case_ids"]),
        "required_surfaces": list(overall["required_surfaces"]),
        "surfaces_covered": list(overall["surfaces_covered"]),
        "missing_surfaces": list(overall["missing_surfaces"]),
        "component_scores": dict(overall["component_scores"]),
        "row_scores": row_scores,
        "surface_scores": surface_scores,
        "overall": overall,
    }


def summarize_acceptance_rows(
    rows: Iterable[dict[str, Any]],
    *,
    required_surfaces: Iterable[str],
) -> dict[str, Any]:
    normalized_rows = [dict(item or {}) for item in list(rows or []) if isinstance(item, dict)]
    required_surface_list = sorted({str(item or "").strip() for item in list(required_surfaces or []) if str(item or "").strip()})
    surfaces_covered = sorted({str(item.get("surface") or "").strip() for item in normalized_rows if str(item.get("surface") or "").strip()})
    evidence_levels_covered = sorted(
        {
            str(item.get("evidence_level") or "").strip()
            for item in normalized_rows
            if str(item.get("evidence_level") or "").strip()
        }
    )
    evidence_pass_levels_covered = sorted(
        {
            level
            for level in (_evidence_pass_level(str(item.get("evidence_level") or "").strip()) for item in normalized_rows)
            if level
        },
        key=lambda item: PASS_LEVEL_ORDER[item],
    )
    evidence_pass_level = ""
    for item in normalized_rows:
        level = _evidence_pass_level(str(item.get("evidence_level") or "").strip())
        if not level:
            evidence_pass_level = ""
            break
        if not evidence_pass_level or PASS_LEVEL_ORDER[level] < PASS_LEVEL_ORDER[evidence_pass_level]:
            evidence_pass_level = level
    contract_failures: list[dict[str, Any]] = []
    for item in normalized_rows:
        failures = row_contract_failures(item)
        if not failures:
            continue
        contract_failures.append(
            {
                "case_id": str(item.get("case_id") or "").strip(),
                "surface": str(item.get("surface") or "").strip(),
                "failures": failures,
            }
        )
    contract_passed = not contract_failures
    required_surface_coverage_passed = all(surface in surfaces_covered for surface in required_surface_list)
    bundle_passed = bool(normalized_rows) and contract_passed and required_surface_coverage_passed and all(
        item.get("acceptance_passed") is True for item in normalized_rows
    )
    operator_passed = bundle_passed and bool(normalized_rows) and all(
        str(item.get("evidence_level") or "").strip() == "operator_live"
        for item in normalized_rows
    )
    return {
        "rows_total": len(normalized_rows),
        "rows_passed": sum(1 for item in normalized_rows if item.get("acceptance_passed") is True),
        "required_surfaces": required_surface_list,
        "surfaces_covered": surfaces_covered,
        "evidence_levels_covered": evidence_levels_covered,
        "evidence_pass_level": evidence_pass_level,
        "evidence_pass_levels_covered": evidence_pass_levels_covered,
        "contract_passed": contract_passed,
        "bundle_passed": bundle_passed,
        "operator_passed": operator_passed,
        "contract_failures": contract_failures,
        "required_surface_coverage_passed": required_surface_coverage_passed,
    }
