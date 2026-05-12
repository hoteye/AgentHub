from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence

from .fingerprint import request_fingerprint
from .schema import ReplayCassette, ReplayRound


def _to_object(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{str(key): _to_object(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_to_object(item) for item in value]
    return value


def _request_headers(kwargs: Mapping[str, Any]) -> Dict[str, Any]:
    headers = kwargs.get("extra_headers")
    if not isinstance(headers, dict):
        return {}
    return dict(headers)


def _request_body(kwargs: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        str(key): value
        for key, value in dict(kwargs).items()
        if key != "extra_headers"
    }


def _round_fingerprint(round_item: ReplayRound) -> str:
    recorded = str(round_item.request_fingerprint or "").strip()
    if recorded:
        return recorded
    return request_fingerprint(round_item.request, headers=round_item.request_headers)


def _synthesized_stream_events(round_item: ReplayRound) -> List[Dict[str, Any]]:
    if round_item.response_events:
        return [dict(item) for item in list(round_item.response_events or [])]
    return [{"type": "response.completed", "response": dict(round_item.response)}]


class ReplayMismatchError(RuntimeError):
    pass


class ReplayExhaustedError(RuntimeError):
    pass


@dataclass
class ReplayMatchedRound:
    round_item: ReplayRound
    request: Dict[str, Any]
    headers: Dict[str, Any]


class ReplayResponseStream:
    def __init__(self, round_item: ReplayRound) -> None:
        self._round = round_item
        self._events = _synthesized_stream_events(round_item)

    def __iter__(self) -> Iterator[Any]:
        for event in list(self._events or []):
            yield _to_object(event)

    def get_final_response(self) -> Any:
        return _to_object(self._round.response)


class ReplayRawResponse:
    def __init__(self, round_item: ReplayRound, *, stream: bool = False) -> None:
        self._round = round_item
        self.headers = dict(round_item.response_headers or {})
        self._stream = bool(stream)

    def parse(self) -> Any:
        if self._stream:
            return ReplayResponseStream(self._round)
        return _to_object(self._round.response)


class ReplayStreamingContext:
    def __init__(self, round_item: ReplayRound) -> None:
        self._raw_response = ReplayRawResponse(round_item, stream=True)
        self.headers = dict(self._raw_response.headers)

    def __enter__(self) -> "ReplayStreamingContext":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def parse(self) -> ReplayResponseStream:
        return self._raw_response.parse()


class _ReplayRawResponses:
    def __init__(self, parent: "ReplayResponsesAPI") -> None:
        self._parent = parent

    def create(self, **kwargs: Any) -> ReplayRawResponse:
        matched = self._parent._match(kwargs)
        return ReplayRawResponse(matched.round_item, stream=bool(kwargs.get("stream")))


class _ReplayStreamingResponses:
    def __init__(self, parent: "ReplayResponsesAPI") -> None:
        self._parent = parent

    def create(self, **kwargs: Any) -> ReplayStreamingContext:
        matched = self._parent._match(kwargs)
        return ReplayStreamingContext(matched.round_item)


class ReplayResponsesAPI:
    def __init__(self, cassette: ReplayCassette) -> None:
        self._cassette = cassette
        self._cursor = 0
        self.requests: List[Dict[str, Any]] = []
        self.with_raw_response = _ReplayRawResponses(self)
        self.with_streaming_response = _ReplayStreamingResponses(self)

    def reset(self) -> None:
        self._cursor = 0
        self.requests = []

    def remaining_rounds(self) -> Sequence[ReplayRound]:
        return list(self._cassette.rounds[self._cursor :])

    def _match(self, kwargs: Mapping[str, Any]) -> ReplayMatchedRound:
        if self._cursor >= len(self._cassette.rounds):
            raise ReplayExhaustedError("replay cassette has no remaining rounds")

        body = _request_body(kwargs)
        headers = _request_headers(kwargs)
        actual_fingerprint = request_fingerprint(body, headers=headers)
        expected_round = self._cassette.rounds[self._cursor]
        expected_fingerprint = _round_fingerprint(expected_round)
        if actual_fingerprint != expected_fingerprint:
            raise ReplayMismatchError(
                "replay request fingerprint mismatch for "
                f"round {expected_round.index}: expected {expected_fingerprint}, got {actual_fingerprint}"
            )

        self.requests.append({**body, "extra_headers": dict(headers)})
        self._cursor += 1
        return ReplayMatchedRound(
            round_item=expected_round,
            request=body,
            headers=headers,
        )

    def create(self, **kwargs: Any) -> Any:
        matched = self._match(kwargs)
        if kwargs.get("stream"):
            return ReplayResponseStream(matched.round_item)
        return _to_object(matched.round_item.response)


class ReplayOpenAIClient:
    transport_kind = "replay"
    base_url = "replay://cassette"

    def __init__(self, cassette: ReplayCassette) -> None:
        self.cassette = cassette
        self.responses = ReplayResponsesAPI(cassette)

    def reset(self) -> None:
        self.responses.reset()
