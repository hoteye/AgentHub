from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


_ENVIRONMENT_CONTEXT_PATTERN = re.compile(
    r"<environment_context>(?P<body>.*?)</environment_context>",
    re.DOTALL,
)
_XML_TAG_PATTERN = re.compile(r"<(?P<name>[a-z_]+)>(?P<value>.*?)</(?P=name)>", re.DOTALL)


def detect_local_timezone_name() -> str | None:
    env_tz = str(os.environ.get("TZ") or "").strip()
    if env_tz and env_tz.lower() != "localtime":
        return env_tz
    timezone_file = Path("/etc/timezone")
    try:
        timezone_text = timezone_file.read_text(encoding="utf-8").strip()
    except OSError:
        timezone_text = ""
    if timezone_text:
        return timezone_text
    try:
        localtime_target = Path("/etc/localtime").resolve()
    except OSError:
        localtime_target = None
    if localtime_target is not None:
        marker = "/zoneinfo/"
        target_text = localtime_target.as_posix()
        if marker in target_text:
            zone_name = target_text.split(marker, 1)[1].strip()
            if zone_name:
                return zone_name
    return None


def local_datetime_with_timezone(current_dt: datetime | None = None) -> datetime:
    now = current_dt or datetime.now().astimezone()
    timezone_name = detect_local_timezone_name()
    if timezone_name:
        try:
            return now.astimezone(ZoneInfo(timezone_name))
        except Exception:
            pass
    return now


@dataclass(eq=True)
class NetworkContext:
    allowed_domains: List[str] = field(default_factory=list)
    denied_domains: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "NetworkContext | None":
        if not isinstance(payload, dict):
            return None
        return cls(
            allowed_domains=[str(item) for item in list(payload.get("allowed_domains") or []) if str(item).strip()],
            denied_domains=[str(item) for item in list(payload.get("denied_domains") or []) if str(item).strip()],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed_domains": list(self.allowed_domains),
            "denied_domains": list(self.denied_domains),
        }


@dataclass(eq=True)
class EnvironmentContext:
    cwd: Optional[str] = None
    shell: str = ""
    current_date: Optional[str] = None
    timezone: Optional[str] = None
    network: Optional[NetworkContext] = None
    subagents: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "EnvironmentContext":
        item = dict(payload or {})
        return cls(
            cwd=str(item.get("cwd") or "").strip() or None,
            shell=str(item.get("shell") or "").strip(),
            current_date=str(item.get("current_date") or "").strip() or None,
            timezone=str(item.get("timezone") or "").strip() or None,
            network=NetworkContext.from_dict(item.get("network")),
            subagents=str(item.get("subagents") or "").strip() or None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cwd": self.cwd,
            "shell": self.shell,
            "current_date": self.current_date,
            "timezone": self.timezone,
            "network": None if self.network is None else self.network.to_dict(),
            "subagents": self.subagents,
        }

    def equals_except_shell(self, other: "EnvironmentContext") -> bool:
        return (
            self.cwd == other.cwd
            and self.current_date == other.current_date
            and self.timezone == other.timezone
            and self.network == other.network
            and self.subagents == other.subagents
        )

    def diff(self, previous: "EnvironmentContext") -> "EnvironmentContext":
        return EnvironmentContext(
            cwd=self.cwd if self.cwd != previous.cwd else None,
            shell=self.shell,
            current_date=self.current_date,
            timezone=self.timezone,
            network=self.network if self.network != previous.network else previous.network,
            subagents=self.subagents if self.subagents != previous.subagents else previous.subagents,
        )

    def serialize_to_xml(self) -> str:
        lines: List[str] = []
        if self.cwd:
            lines.append(f"  <cwd>{self.cwd}</cwd>")
        lines.append(f"  <shell>{self.shell}</shell>")
        if self.current_date:
            lines.append(f"  <current_date>{self.current_date}</current_date>")
        if self.timezone:
            lines.append(f"  <timezone>{self.timezone}</timezone>")
        if self.network is not None:
            lines.append('  <network enabled="true">')
            for item in self.network.allowed_domains:
                lines.append(f"    <allowed>{item}</allowed>")
            for item in self.network.denied_domains:
                lines.append(f"    <denied>{item}</denied>")
            lines.append("  </network>")
        if self.subagents:
            lines.append("  <subagents>")
            lines.extend(f"    {line}" for line in self.subagents.splitlines() if line.strip())
            lines.append("  </subagents>")
        return "<environment_context>\n" + "\n".join(lines) + "\n</environment_context>"


def build_environment_context_snapshot(
    *,
    cwd: str | None,
    shell: str,
    network_access: bool,
    current_dt: datetime | None = None,
    allowed_domains: Optional[List[str]] = None,
    denied_domains: Optional[List[str]] = None,
    subagents: Optional[str] = None,
) -> Dict[str, Any]:
    now = current_dt if current_dt is not None else local_datetime_with_timezone()
    network = None
    if network_access:
        network = NetworkContext(
            allowed_domains=[str(item) for item in list(allowed_domains or []) if str(item).strip()],
            denied_domains=[str(item) for item in list(denied_domains or []) if str(item).strip()],
        )
    context = EnvironmentContext(
        cwd=str(cwd or "").strip() or None,
        shell=str(shell or "").strip(),
        current_date=now.date().isoformat(),
        timezone=str(now.tzinfo or "").strip() or None,
        network=network,
        subagents=str(subagents or "").strip() or None,
    )
    return context.to_dict()


def render_environment_context_update_message(
    previous: Dict[str, Any] | None,
    current: Dict[str, Any],
) -> str | None:
    current_context = EnvironmentContext.from_dict(current)
    if not previous:
        return current_context.serialize_to_xml()
    previous_context = EnvironmentContext.from_dict(previous)
    # Always return full context for OpenAI-compatible relay compatibility
    # Some relays require environment_context in every turn, even if unchanged
    return current_context.serialize_to_xml()


def environment_context_marker_offset(text: str) -> int | None:
    source = str(text or "")
    idx = source.find("<environment_context>")
    return idx if idx >= 0 else None


def environment_contract(snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    context = EnvironmentContext.from_dict(snapshot)
    return {
        "cwd": str(context.cwd or "").strip(),
        "current_date": str(context.current_date or "").strip(),
        "timezone": str(context.timezone or "").strip(),
    }


def extract_environment_context_from_text(text: str) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for block_match in _ENVIRONMENT_CONTEXT_PATTERN.finditer(str(text or "")):
        block_values: Dict[str, Any] = {}
        block_text = str(block_match.group("body") or "")
        for match in _XML_TAG_PATTERN.finditer(block_text):
            name = str(match.group("name") or "").strip()
            value = str(match.group("value") or "").strip()
            if name in {"cwd", "shell", "current_date", "timezone"} and value:
                block_values[name] = value
        if block_values:
            values = block_values
    return values


def extract_environment_contract_from_input_items(
    items: List[Dict[str, Any]] | None,
    *,
    fallback: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    latest: Dict[str, Any] = {}
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_text = str(block.get("text") or "").strip()
                if block_text:
                    parts.append(block_text)
            text = "\n".join(parts)
        else:
            text = ""
        extracted = extract_environment_context_from_text(text)
        if extracted:
            latest = extracted
    if latest:
        return environment_contract(latest)
    return environment_contract(fallback)
