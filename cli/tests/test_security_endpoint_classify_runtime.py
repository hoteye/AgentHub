import pytest

from cli.agent_cli.providers.security_endpoint_classify_runtime import (
    classify_endpoint_host,
    no_auth_guardrail_pass,
    no_auth_guardrail_reason,
)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", "loopback"),
        ("127.0.0.1", "loopback"),
        ("10.1.2.3", "rfc1918"),
        ("169.254.1.2", "link_local"),
        ("fc00::1", "private"),
        ("8.8.8.8", "public"),
        ("api.example.com", "public"),
    ],
)
def test_classify_endpoint_host_expected_buckets(host: str, expected: str) -> None:
    assert classify_endpoint_host(host) == expected


def test_classify_endpoint_host_hostname_fallback_is_public() -> None:
    assert classify_endpoint_host("mybox.local") == "public"


def test_no_auth_guardrail_with_non_none_auth_mode_is_blocked() -> None:
    assert (
        no_auth_guardrail_pass(
            auth_mode="api_key",
            allow_no_auth=False,
            base_url="http://127.0.0.1:8000/v1",
        )
        is False
    )
    assert no_auth_guardrail_reason(
        auth_mode="api_key",
        allow_no_auth=False,
        base_url="http://127.0.0.1:8000/v1",
    ) == "auth_mode_not_none"


def test_no_auth_guardrail_allow_flag_overrides_public_endpoint_block() -> None:
    assert (
        no_auth_guardrail_pass(
            auth_mode="none",
            allow_no_auth=True,
            base_url="https://api.example.com/v1",
        )
        is True
    )
    assert no_auth_guardrail_reason(
        auth_mode="none",
        allow_no_auth=True,
        base_url="https://api.example.com/v1",
    ) == "explicit_allow_no_auth"


@pytest.mark.parametrize(
    ("base_url", "expected_reason"),
    [
        ("http://127.0.0.1:11434/v1", "loopback_endpoint"),
        ("http://10.0.0.5:8080/v1", "rfc1918_endpoint"),
        ("http://169.254.10.20:8080/v1", "link_local_endpoint"),
        ("http://[fc00::1]:8080/v1", "private_endpoint"),
    ],
)
def test_no_auth_guardrail_auto_allows_local_private_endpoints(
    base_url: str, expected_reason: str
) -> None:
    assert (
        no_auth_guardrail_pass(
            auth_mode="none",
            allow_no_auth=False,
            base_url=base_url,
        )
        is True
    )
    assert no_auth_guardrail_reason(
        auth_mode="none",
        allow_no_auth=False,
        base_url=base_url,
    ) == expected_reason


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.example.com/v1",
        "http://8.8.8.8:8080/v1",
        "http://mybox.local:8080/v1",
    ],
)
def test_no_auth_guardrail_blocks_public_endpoints_without_allow_flag(base_url: str) -> None:
    assert (
        no_auth_guardrail_pass(
            auth_mode="none",
            allow_no_auth=False,
            base_url=base_url,
        )
        is False
    )
    assert no_auth_guardrail_reason(
        auth_mode="none",
        allow_no_auth=False,
        base_url=base_url,
    ) == "public_endpoint_requires_auth"
