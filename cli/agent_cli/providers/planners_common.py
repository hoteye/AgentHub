from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.host_platform import HostPlatform, current_host_platform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.planner_input_items import PlannerInputItemsMixin
from cli.agent_cli.providers.planner_status import PlannerStatusMixin
from cli.agent_cli.providers.model_routing import RouteResolution


class BasePlanner(PlannerStatusMixin, PlannerInputItemsMixin):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        host_platform: HostPlatform | None = None,
        cwd: str | None = None,
        plugin_manager_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config
        self.host_platform = host_platform or current_host_platform()
        self.cwd = cwd
        self.plugin_manager_factory = plugin_manager_factory
        self._route_resolution_cache: Dict[tuple[str, str, int | None, bool], RouteResolution] = {}
        self._delegation_resolution_cache: Dict[tuple[str, int | None, bool], RouteResolution] = {}
