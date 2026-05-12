from __future__ import annotations

from typing import Any, Dict


def assign_runtime_delegated_methods(runtime_cls: Any, methods: Dict[str, Any]) -> None:
    for name, value in methods.items():
        setattr(runtime_cls, name, value)
