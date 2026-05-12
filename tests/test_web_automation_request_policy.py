from __future__ import annotations

import pytest

from shared.web_automation.request_policy import (
    is_persistent_browser_profile_mutation,
    normalize_browser_request_path,
    resolve_requested_browser_profile,
)


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        ("tabs", "/tabs"),
        ("/tabs/", "/tabs"),
        ("/", "/"),
        ("", ""),
    ],
)
def test_normalize_browser_request_path(raw_path: str, expected: str) -> None:
    assert normalize_browser_request_path(raw_path) == expected


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/profiles/create", True),
        ("POST", "/reset-profile/", True),
        ("DELETE", "/profiles/review", True),
        ("GET", "/profiles", False),
        ("DELETE", "/profiles/review/tabs", False),
    ],
)
def test_is_persistent_browser_profile_mutation(method: str, path: str, expected: bool) -> None:
    assert is_persistent_browser_profile_mutation(method, path) is expected


@pytest.mark.parametrize(
    ("query", "body", "profile", "expected"),
    [
        ({"profile": "review"}, {"profile": "user"}, "openclaw", "review"),
        ({}, {"profile": "user"}, "openclaw", "user"),
        ({}, {}, "openclaw", "openclaw"),
        ({}, {}, None, None),
    ],
)
def test_resolve_requested_browser_profile_prefers_query_then_body_then_explicit(
    query: dict[str, str],
    body: dict[str, str],
    profile: str | None,
    expected: str | None,
) -> None:
    assert resolve_requested_browser_profile(query=query, body=body, profile=profile) == expected
