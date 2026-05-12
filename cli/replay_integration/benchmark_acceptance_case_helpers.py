from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


REQUIRED_ROW_FIELDS = (
    "case_id",
    "surface",
    "tool_name_expected",
    "tool_name_actual",
    "tool_name_correct",
    "arguments_correct",
    "result_usable",
    "time_to_first_event_ms",
    "time_to_first_tool_ms",
    "acceptance_passed",
    "evidence_level",
)
ALLOWED_EVIDENCE_LEVELS = frozenset({"synthetic", "fixture_live", "operator_live"})
PASS_LEVEL_FIELDS = {
    "contract": "contract_passed",
    "bundle": "bundle_passed",
    "operator": "operator_passed",
}
EVIDENCE_LEVEL_PASS_LEVELS = {
    "synthetic": "contract",
    "fixture_live": "bundle",
    "operator_live": "operator",
}
PASS_LEVEL_ORDER = {
    "contract": 0,
    "bundle": 1,
    "operator": 2,
}


@dataclass(frozen=True)
class BenchmarkCaseSpec:
    case_id: str
    surface: str
    expected_tool_name: str
    expected_argument_options: tuple[dict[str, Any], ...]
    expected_result_fragment: str

    @property
    def expected_argument_subset(self) -> dict[str, Any]:
        return dict(self.expected_argument_options[0]) if self.expected_argument_options else {}


_BENCHMARK_CASE_SPECS: tuple[BenchmarkCaseSpec, ...] = (
    BenchmarkCaseSpec(
        case_id="shell_pwd",
        surface="shell",
        expected_tool_name="exec_command",
        expected_argument_options=({"cmd": "pwd"},),
        expected_result_fragment="/tmp/agenthub_operator_live/shell_pwd",
    ),
    BenchmarkCaseSpec(
        case_id="write_readme",
        surface="write",
        expected_tool_name="apply_patch",
        expected_argument_options=(
            {"patch": "*** Begin Patch"},
            {"file_path": "README.md", "content": "hello"},
        ),
        expected_result_fragment="README.md",
    ),
    BenchmarkCaseSpec(
        case_id="edit_settings",
        surface="edit",
        expected_tool_name="apply_patch",
        expected_argument_options=(
            {"patch": "*** Update File: settings.toml"},
            {
                "file_path": "settings.toml",
                "old_string": 'mode = "dev"',
                "new_string": 'mode = "prod"',
            },
        ),
        expected_result_fragment="settings.toml",
    ),
    BenchmarkCaseSpec(
        case_id="search_weather",
        surface="search",
        expected_tool_name="web_search",
        expected_argument_options=({"query": "Shanghai weather"},),
        expected_result_fragment="Shanghai",
    ),
    BenchmarkCaseSpec(
        case_id="delegate_probe",
        surface="agent_delegation",
        expected_tool_name="spawn_agent",
        expected_argument_options=(
            {"agent_type": "explorer"},
            {"prompt": "worker summary"},
            {"prompt": "只回复 ok"},
        ),
        expected_result_fragment="worker summary",
    ),
)


def list_benchmark_case_specs() -> list[BenchmarkCaseSpec]:
    return list(_BENCHMARK_CASE_SPECS)


def get_benchmark_case_spec(case_id: str) -> BenchmarkCaseSpec:
    normalized_case_id = str(case_id or "").strip()
    for spec in _BENCHMARK_CASE_SPECS:
        if spec.case_id == normalized_case_id:
            return spec
    raise KeyError(f"unknown benchmark case id: {case_id!r}")


def required_surfaces_for_benchmark(case_ids: Iterable[str] | None = None) -> list[str]:
    if case_ids is None:
        return sorted({item.surface for item in _BENCHMARK_CASE_SPECS})
    requested = {str(item or "").strip() for item in list(case_ids or []) if str(item or "").strip()}
    return sorted({item.surface for item in _BENCHMARK_CASE_SPECS if item.case_id in requested})


def list_benchmark_case_ids() -> list[str]:
    return [item.case_id for item in _BENCHMARK_CASE_SPECS]


def row_contract_failures(row: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    normalized = dict(row or {})
    for field in REQUIRED_ROW_FIELDS:
        if field not in normalized:
            failures.append(f"missing:{field}")
    surface = str(normalized.get("surface") or "").strip()
    if not surface:
        failures.append("invalid:surface")
    evidence_level = str(normalized.get("evidence_level") or "").strip()
    if evidence_level not in ALLOWED_EVIDENCE_LEVELS:
        failures.append("invalid:evidence_level")
    for field in ("tool_name_correct", "arguments_correct", "result_usable", "acceptance_passed"):
        if field in normalized and not isinstance(normalized.get(field), bool):
            failures.append(f"invalid:{field}")
    for field in ("time_to_first_event_ms", "time_to_first_tool_ms"):
        value = normalized.get(field)
        if value is None:
            continue
        if not isinstance(value, int):
            failures.append(f"invalid:{field}")
            continue
        if value < 0:
            failures.append(f"invalid:{field}_negative")
    return failures


def _evidence_pass_level(evidence_level: str) -> str:
    normalized = str(evidence_level or "").strip()
    return EVIDENCE_LEVEL_PASS_LEVELS.get(normalized, "")


def _benchmark_case_order(case_id: str) -> int:
    normalized_case_id = str(case_id or "").strip()
    for index, spec in enumerate(_BENCHMARK_CASE_SPECS):
        if spec.case_id == normalized_case_id:
            return index
    return len(_BENCHMARK_CASE_SPECS)


def _sorted_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item or {}) for item in list(rows or []) if isinstance(item, dict)],
        key=lambda item: (
            _benchmark_case_order(str(item.get("case_id") or "").strip()),
            str(item.get("case_id") or "").strip(),
        ),
    )
