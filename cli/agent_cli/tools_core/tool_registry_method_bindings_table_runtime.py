from __future__ import annotations

from typing import Any


def bind_method_table(registry_cls: Any, *, method_bindings: tuple[tuple[str, Any], ...]) -> None:
    for name, value in method_bindings:
        setattr(registry_cls, name, value)
