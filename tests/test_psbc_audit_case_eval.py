import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.psbc_audit_case_eval import DEFAULT_CASE_FILE, _load_cases, evaluate_case

class PsbcAuditCaseEvalTest(unittest.TestCase):
    def test_case_fixture_loads(self):
        cases = _load_cases(DEFAULT_CASE_FILE)
        self.assertGreaterEqual(len(cases), 5)
        self.assertTrue(all(case.case_id for case in cases))
        self.assertTrue(all(case.oracle_paths for case in cases))

    def test_oracle_answer_contains_expected_keywords_for_reporting_case(self):
        cases = {case.case_id: case for case in _load_cases(DEFAULT_CASE_FILE)}
        result = evaluate_case(cases["outsourcing_reporting_gap"])

        oracle = result["oracle"]
        self.assertGreaterEqual(int(oracle["read_ok_count"]), 1)
        self.assertIn("信息科技外包活动清单", oracle["answer"]["answer_text"])
        self.assertIn("金融科技部", oracle["answer"]["answer_text"])
        self.assertGreaterEqual(float(oracle["answer_evaluation"]["score"]), 0.45)

    def test_oracle_answer_contains_expected_keywords_for_ukey_case(self):
        cases = {case.case_id: case for case in _load_cases(DEFAULT_CASE_FILE)}
        result = evaluate_case(cases["ukey_borrowing"])

        oracle = result["oracle"]
        self.assertGreaterEqual(int(oracle["read_ok_count"]), 1)
        self.assertIn("严禁随意使用他人UKey", oracle["answer"]["answer_text"])
        self.assertIn("责任部门", oracle["answer"]["answer_text"])
        self.assertGreaterEqual(float(oracle["answer_evaluation"]["score"]), 0.45)

    def test_oracle_least_privilege_case_uses_correct_issue_label(self):
        cases = {case.case_id: case for case in _load_cases(DEFAULT_CASE_FILE)}
        result = evaluate_case(cases["outsourcing_least_privilege"])

        oracle = result["oracle"]
        self.assertEqual(oracle["answer"]["issue_label"], "最小授权控制不到位")
        self.assertIn("最小授权原则", oracle["answer"]["answer_text"])
