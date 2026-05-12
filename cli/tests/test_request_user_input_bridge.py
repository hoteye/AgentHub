from __future__ import annotations

from cli.agent_cli.ui.request_user_input_bridge import RequestUserInputBridge


def _payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            }
        ]
    }


def test_start_request_normalizes_questions_and_tracks_pending() -> None:
    bridge = RequestUserInputBridge(request_id_factory=lambda: "rui_1")

    pending = bridge.start_request(_payload())

    assert pending.request_id == "rui_1"
    assert pending.questions[0]["id"] == "confirm_path"
    assert pending.questions[0]["is_other"] is True
    assert pending.question_ids == {"confirm_path"}
    assert bridge.pending_request("rui_1") is pending
    assert bridge.snapshot() == [pending]


def test_build_handler_round_trip_normalizes_and_filters_answers() -> None:
    bridge = RequestUserInputBridge(request_id_factory=lambda: "rui_2")
    seen: list[str] = []

    def _on_request(pending) -> None:
        seen.append(pending.request_id)
        bridge.resolve_request(
            pending.request_id,
            {
                "answers": {
                    "confirm_path": {"answer": "yes"},
                    "ignored_key": {"answers": ["no"]},
                }
            },
        )

    handler = bridge.build_handler(on_request=_on_request)
    response = handler(_payload())

    assert seen == ["rui_2"]
    assert response == {"answers": {"confirm_path": {"answers": ["yes"]}}}
    assert bridge.snapshot() == []


def test_build_handler_on_request_exception_returns_none_and_cleans_up() -> None:
    bridge = RequestUserInputBridge(request_id_factory=lambda: "rui_3")

    def _on_request(_pending) -> None:
        raise RuntimeError("boom")

    handler = bridge.build_handler(on_request=_on_request)
    response = handler(_payload())

    assert response is None
    assert bridge.snapshot() == []


def test_resolve_request_unknown_id_returns_false() -> None:
    bridge = RequestUserInputBridge()

    ok = bridge.resolve_request(
        "missing",
        {"answers": {"confirm_path": {"answers": ["yes"]}}},
    )

    assert ok is False


def test_cancel_request_unknown_id_returns_false() -> None:
    bridge = RequestUserInputBridge()

    ok = bridge.cancel_request("missing")

    assert ok is False


def test_wait_for_response_timeout_returns_none() -> None:
    bridge = RequestUserInputBridge(request_id_factory=lambda: "rui_4")
    bridge.start_request(_payload())

    response = bridge.wait_for_response("rui_4", timeout_seconds=0.01)

    assert response is None
    assert bridge.pending_request("rui_4") is not None


def test_wait_for_response_returns_none_after_cancel() -> None:
    bridge = RequestUserInputBridge(request_id_factory=lambda: "rui_5")
    bridge.start_request(_payload())
    assert bridge.cancel_request("rui_5") is True

    response = bridge.wait_for_response("rui_5", timeout_seconds=0.01)

    assert response is None


def test_cancel_all_marks_requests_and_returns_count() -> None:
    request_ids = iter(["rui_6", "rui_7"])
    bridge = RequestUserInputBridge(request_id_factory=lambda: next(request_ids))
    first = bridge.start_request(_payload())
    second = bridge.start_request(_payload())

    cancelled_count = bridge.cancel_all()

    assert cancelled_count == 2
    assert first.cancelled is True
    assert second.cancelled is True
    assert first.response_event.is_set() is True
    assert second.response_event.is_set() is True

