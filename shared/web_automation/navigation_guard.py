from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Callable, Iterable
from urllib.parse import urlparse

from shared.web_automation.config import BrowserAutomationConfig

ALLOWED_NETWORK_PROTOCOLS = frozenset({"http", "https"})
ALLOWED_BROWSER_ENDPOINT_PROTOCOLS = frozenset({"http", "https", "ws", "wss"})
ALLOWED_NON_NETWORK_PROTOCOLS = frozenset({"file", "data"})
ALLOWED_ABOUT_URLS = frozenset({"about:blank"})

HostResolver = Callable[[str], list[str]]


class InvalidBrowserNavigationUrlError(ValueError):
    pass


@dataclass(frozen=True)
class BrowserNavigationPolicy:
    allow_hosts: tuple[str, ...] = field(default_factory=tuple)
    block_hosts: tuple[str, ...] = field(default_factory=tuple)
    allow_private_network: bool = False


def navigation_policy_from_config(config: BrowserAutomationConfig) -> BrowserNavigationPolicy:
    return BrowserNavigationPolicy(
        allow_hosts=tuple(_normalize_rule(rule) for rule in config.allow_hosts if _normalize_rule(rule)),
        block_hosts=tuple(_normalize_rule(rule) for rule in config.block_hosts if _normalize_rule(rule)),
        allow_private_network=bool(config.allow_private_network),
    )


def assert_browser_navigation_allowed(
    url: str,
    *,
    policy: BrowserNavigationPolicy | None = None,
    resolver: HostResolver | None = None,
) -> None:
    raw_url = str(url or "").strip()
    if not raw_url:
        raise InvalidBrowserNavigationUrlError("Navigation blocked: url is required")

    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    effective_policy = policy or BrowserNavigationPolicy()

    if raw_url.lower() in ALLOWED_ABOUT_URLS:
        return

    if scheme in ALLOWED_NON_NETWORK_PROTOCOLS:
        return

    if scheme not in ALLOWED_NETWORK_PROTOCOLS:
        rendered = f"{scheme}:" if scheme else raw_url
        raise InvalidBrowserNavigationUrlError(
            f'Navigation blocked: unsupported protocol "{rendered}"'
        )

    _assert_host_allowed(
        hostname=_normalize_host(parsed.hostname or ""),
        policy=effective_policy,
        resolver=resolver,
        error_prefix="Navigation blocked",
        allow_loopback_private=False,
    )


def assert_browser_endpoint_allowed(
    url: str,
    *,
    policy: BrowserNavigationPolicy | None = None,
    resolver: HostResolver | None = None,
) -> None:
    raw_url = str(url or "").strip()
    if not raw_url:
        raise InvalidBrowserNavigationUrlError("Browser endpoint blocked: url is required")

    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    effective_policy = policy or BrowserNavigationPolicy()

    if scheme not in ALLOWED_BROWSER_ENDPOINT_PROTOCOLS:
        rendered = f"{scheme}:" if scheme else raw_url
        raise InvalidBrowserNavigationUrlError(
            f'Browser endpoint blocked: unsupported protocol "{rendered}"'
        )

    _assert_host_allowed(
        hostname=_normalize_host(parsed.hostname or ""),
        policy=effective_policy,
        resolver=resolver,
        error_prefix="Browser endpoint blocked",
        allow_loopback_private=True,
    )


def assert_browser_navigation_result_allowed(
    url: str,
    *,
    policy: BrowserNavigationPolicy | None = None,
    resolver: HostResolver | None = None,
) -> None:
    raw_url = str(url or "").strip()
    if not raw_url:
        return
    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    if raw_url.lower() in ALLOWED_ABOUT_URLS or scheme in ALLOWED_NETWORK_PROTOCOLS or scheme in ALLOWED_NON_NETWORK_PROTOCOLS:
        assert_browser_navigation_allowed(raw_url, policy=policy, resolver=resolver)


def _assert_host_allowed(
    *,
    hostname: str,
    policy: BrowserNavigationPolicy,
    resolver: HostResolver | None,
    error_prefix: str,
    allow_loopback_private: bool,
) -> None:
    if not hostname:
        raise InvalidBrowserNavigationUrlError(f"{error_prefix}: host is required for network URLs")

    matched_block = _find_matching_rule(hostname, policy.block_hosts)
    if matched_block:
        raise InvalidBrowserNavigationUrlError(
            f'{error_prefix}: host "{hostname}" matches block_hosts rule "{matched_block}"'
        )

    if policy.allow_hosts:
        matched_allow = _find_matching_rule(hostname, policy.allow_hosts)
        if not matched_allow:
            raise InvalidBrowserNavigationUrlError(
                f'{error_prefix}: host "{hostname}" is not in allow_hosts'
            )

    if policy.allow_private_network:
        return

    if allow_loopback_private and _is_loopback_host(hostname, resolver=resolver):
        return

    if _is_private_host(hostname, resolver=resolver):
        raise InvalidBrowserNavigationUrlError(
            f'{error_prefix}: private network host "{hostname}" is not allowed; '
            "set allow_private_network=true to permit it"
        )


def _is_private_host(hostname: str, *, resolver: HostResolver | None = None) -> bool:
    if _is_local_hostname(hostname):
        return True

    literal_ip = _parse_ip(hostname)
    if literal_ip is not None:
        return _is_private_ip(literal_ip)

    for resolved in _resolve_host_ips(hostname, resolver=resolver):
        ip = _parse_ip(resolved)
        if ip is not None and _is_private_ip(ip):
            return True
    return False


def _is_loopback_host(hostname: str, *, resolver: HostResolver | None = None) -> bool:
    if _is_local_hostname(hostname):
        return True
    literal_ip = _parse_ip(hostname)
    if literal_ip is not None:
        return bool(literal_ip.is_loopback)
    resolved = _resolve_host_ips(hostname, resolver=resolver)
    if not resolved:
        return False
    saw_ip = False
    for item in resolved:
        ip = _parse_ip(item)
        if ip is None:
            continue
        saw_ip = True
        if not ip.is_loopback:
            return False
    return saw_ip


def _resolve_host_ips(hostname: str, *, resolver: HostResolver | None = None) -> list[str]:
    if resolver is not None:
        return [str(item).strip() for item in resolver(hostname) if str(item).strip()]
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    addresses: list[str] = []
    seen: set[str] = set()
    for item in infos:
        sockaddr = item[4]
        if not sockaddr:
            continue
        address = str(sockaddr[0]).strip()
        if address and address not in seen:
            seen.add(address)
            addresses.append(address)
    return addresses


def _is_local_hostname(hostname: str) -> bool:
    return hostname == "localhost" or hostname.endswith(".localhost")


def _is_private_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
    )


def _parse_ip(value: str) -> ipaddress._BaseAddress | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _find_matching_rule(hostname: str, rules: Iterable[str]) -> str | None:
    for rule in rules:
        normalized_rule = _normalize_rule(rule)
        if normalized_rule and _host_matches_rule(hostname, normalized_rule):
            return normalized_rule
    return None


def _host_matches_rule(hostname: str, rule: str) -> bool:
    if rule.startswith("*."):
        base = rule[2:]
        return hostname == base or hostname.endswith(f".{base}")
    if rule.startswith("."):
        base = rule[1:]
        return hostname == base or hostname.endswith(f".{base}")
    return hostname == rule


def _normalize_host(value: str) -> str:
    return str(value or "").strip().lower().rstrip(".")


def _normalize_rule(rule: str) -> str:
    text = _normalize_host(rule)
    if text.startswith("*."):
        return f"*.{text[2:]}"
    return text
