#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE_FILE = ROOT / "tests" / "data" / "psbc_audit_cases.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.psbc_audit_case_eval_draft_helpers import (  # noqa: E402
    _draft_answer,
    _evidence_prompt_blocks,
    _extract_json_payload,
    _format_llm_error,
    _heuristic_draft_answer,
    _llm_draft_answer,
    _llm_text,
    _provider_wire_mode,
    _retryable_llm_error,
)
from tools.psbc_audit_case_eval_eval_helpers import (  # noqa: E402
    _evaluate_live,
    _evaluate_oracle,
    _evaluate_text,
    _keyword_hits,
    _read_evidence,
    evaluate_case,
)
from tools.psbc_audit_case_eval_model_helpers import (  # noqa: E402
    AuditCase,
    DraftResult,
    _dedupe,
    _extract_responsibility_subjects,
    _issue_label,
    _load_cases,
    _normalize_text,
    _pick_evidence_lines,
    _query_terms,
    _shorten,
    _split_evidence_lines,
)
from tools.psbc_audit_case_eval_reporting_helpers import SECTION_DIVIDER, _print_human, _summary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate psbc_policy with real audit cases.")
    parser.add_argument("--case-file", default=str(DEFAULT_CASE_FILE), help="JSON case file path.")
    parser.add_argument("--case-id", action="append", default=[], help="Only run specific case id. Repeatable.")
    parser.add_argument(
        "--draft-mode",
        choices=("heuristic", "llm"),
        default="heuristic",
        help="How to draft answers from retrieved evidence.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human-readable output.")
    args = parser.parse_args()

    cases = _load_cases(Path(args.case_file))
    selected = set(args.case_id or [])
    if selected:
        cases = [case for case in cases if case.case_id in selected]
    results = [evaluate_case(case, draft_mode=args.draft_mode) for case in cases]

    if args.json:
        print(json.dumps({"summary": _summary(results), "results": results}, ensure_ascii=False, indent=2))
    else:
        _print_human(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
