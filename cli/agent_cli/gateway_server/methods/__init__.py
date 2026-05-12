from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping


GatewayMethodHandler = Callable[..., Dict[str, Any]]
GatewayHandlerMap = Dict[str, GatewayMethodHandler]


@dataclass(frozen=True)
class GatewayMethodFamily:
    family_name: str
    methods: tuple[str, ...]
    handlers: GatewayHandlerMap


def make_stub_handler(
    *,
    family_name: str,
    method_name: str,
    summary: str,
) -> GatewayMethodHandler:
    def _handler(**kwargs: Any) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": "stub",
            "family": family_name,
            "method": method_name,
            "summary": summary,
            "params": dict(kwargs.get("params") or {}),
        }

    _handler.__name__ = method_name.replace(".", "_")
    return _handler


def build_family(
    *,
    family_name: str,
    method_summaries: Mapping[str, str],
) -> GatewayMethodFamily:
    handlers = {
        method_name: make_stub_handler(
            family_name=family_name,
            method_name=method_name,
            summary=summary,
        )
        for method_name, summary in method_summaries.items()
    }
    return GatewayMethodFamily(
        family_name=family_name,
        methods=tuple(method_summaries.keys()),
        handlers=handlers,
    )


def merge_handler_maps(families: Iterable[GatewayMethodFamily]) -> GatewayHandlerMap:
    merged: GatewayHandlerMap = {}
    for family in families:
        overlap = set(merged).intersection(family.handlers)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"duplicate gateway method registrations: {names}")
        merged.update(family.handlers)
    return merged
