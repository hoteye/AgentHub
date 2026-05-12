from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    description: str
    api_version: str = "1"
    plugin_kind: str = "generic"
    distribution: str = "bundled"
    min_host_version: str = "0.1.0"
    enabled_by_default: bool = False
    commercial: bool = False
    dependencies: List[str] = field(default_factory=list)
    capability_declarations: List[Dict[str, Any]] = field(default_factory=list)
