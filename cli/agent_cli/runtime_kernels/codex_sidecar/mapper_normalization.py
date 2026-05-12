from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _field(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload:
            return payload.get(name)
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _snake_case(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    chars: list[str] = []
    previous_lower_or_digit = False
    for char in text:
        if char in {"-", " "}:
            chars.append("_")
            previous_lower_or_digit = False
            continue
        if char.isupper() and previous_lower_or_digit:
            chars.append("_")
        chars.append(char.lower())
        previous_lower_or_digit = char.islower() or char.isdigit()
    return "".join(chars)


def _status(value: Any, *, default: str = "") -> str:
    normalized = _snake_case(value)
    return normalized or default


def _id_from_item(item: dict[str, Any]) -> str:
    return _text(_field(item, "id", "itemId", "item_id"))


def _turn_id_from_payload(payload: dict[str, Any]) -> str:
    turn = _mapping(payload.get("turn"))
    return _text(
        _field(
            payload,
            "turnId",
            "turn_id",
        )
        or _field(turn, "id", "turnId", "turn_id")
    )


def _thread_id_from_payload(payload: dict[str, Any]) -> str:
    return _text(_field(payload, "threadId", "thread_id"))


def _notification_item(payload: dict[str, Any]) -> dict[str, Any]:
    return _mapping(payload.get("item"))
