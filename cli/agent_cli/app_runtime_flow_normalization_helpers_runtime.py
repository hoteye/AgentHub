from __future__ import annotations


def normalize_transcript_search_key(key: str) -> str:
    return str(key or "").strip().lower()


def normalize_transcript_search_text(text: str) -> str:
    return str(text or "")


def normalize_runtime_request_text(text: str) -> str:
    return str(text or "").strip()


def normalize_screen_mode(screen_mode: str) -> str:
    return "transcript" if str(screen_mode or "").strip().lower() == "transcript" else "prompt"


def normalize_request_user_input_cancel_reason(reason: str) -> str:
    return str(reason or "").strip().lower().replace("-", "_").replace(" ", "_")


__all__ = [
    "normalize_request_user_input_cancel_reason",
    "normalize_runtime_request_text",
    "normalize_screen_mode",
    "normalize_transcript_search_key",
    "normalize_transcript_search_text",
]
