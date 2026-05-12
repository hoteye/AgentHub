import unittest

from cli.replay_integration.fingerprint import build_request_signature, request_fingerprint

class ReplayFingerprintTest(unittest.TestCase):
    def test_request_fingerprint_is_stable_across_header_order(self) -> None:
        request = {
            "model": "gpt-5.4",
            "instructions": "system",
            "input": [{"role": "user", "content": "hello"}],
            "tools": [{"name": "exec_command"}],
        }
        left = request_fingerprint(request, headers={"session_id": "thread_1", "x-reference-turn-state": "ts_1"})
        right = request_fingerprint(request, headers={"x-reference-turn-state": "ts_1", "session_id": "thread_1"})
        self.assertEqual(left, right)

    def test_request_signature_changes_when_input_changes(self) -> None:
        first = request_fingerprint({"model": "gpt-5.4", "input": [{"role": "user", "content": "hello"}]})
        second = request_fingerprint({"model": "gpt-5.4", "input": [{"role": "user", "content": "goodbye"}]})
        self.assertNotEqual(first, second)

    def test_build_request_signature_filters_to_semantic_fields(self) -> None:
        signature = build_request_signature(
            {
                "model": "gpt-5.4",
                "input": [{"role": "user", "content": "hello"}],
                "store": False,
                "stream": True,
            },
            headers={"session_id": "thread_1", "other": "ignored"},
        )
        self.assertEqual(signature["request"], {"model": "gpt-5.4", "input": [{"role": "user", "content": "hello"}]})
        self.assertEqual(signature["headers"], {"session_id": "thread_1"})
