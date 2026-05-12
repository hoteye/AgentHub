from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

RFC1918_V4_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)

AUTO_ALLOW_NO_AUTH_CLASSIFICATIONS = frozenset(
    {
        "loopback",
        "rfc1918",
        "link_local",
        "private",
    }
)


def host_from_base_url(base_url: str | None) -> str:
    text = str(base_url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"http://{text}")
    return str(parsed.hostname or "").strip().lower()


def classify_endpoint_host(host: str) -> str:
    token = str(host or "").strip().lower()
    if not token:
        return "unknown"
    if token == "localhost":
        return "loopback"
    try:
        ip = ipaddress.ip_address(token)
    except ValueError:
        # Conservative fallback for non-IP hosts: treat as non-local until explicitly allowed.
        return "public"

    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if ip.version == 4 and any(ip in network for network in RFC1918_V4_NETWORKS):
        return "rfc1918"
    if ip.is_private:
        # Covers IPv6 ULA (fc00::/7) and other non-public private ranges.
        return "private"
    return "public"


def classify_endpoint_base_url(base_url: str | None) -> str:
    return classify_endpoint_host(host_from_base_url(base_url))


def no_auth_guardrail_pass(
    *,
    auth_mode: str,
    allow_no_auth: bool,
    base_url: str | None,
) -> bool:
    normalized_mode = str(auth_mode or "").strip().lower()
    if normalized_mode != "none":
        return False
    if allow_no_auth:
        return True
    endpoint_classification = classify_endpoint_base_url(base_url)
    return endpoint_classification in AUTO_ALLOW_NO_AUTH_CLASSIFICATIONS


def no_auth_guardrail_reason(
    *,
    auth_mode: str,
    allow_no_auth: bool,
    base_url: str | None,
) -> str:
    normalized_mode = str(auth_mode or "").strip().lower()
    if normalized_mode != "none":
        return "auth_mode_not_none"
    if allow_no_auth:
        return "explicit_allow_no_auth"
    endpoint_classification = classify_endpoint_base_url(base_url)
    if endpoint_classification in AUTO_ALLOW_NO_AUTH_CLASSIFICATIONS:
        return f"{endpoint_classification}_endpoint"
    return "public_endpoint_requires_auth"
