from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from cli.agent_cli.models import ToolEvent

from . import runtime_facade_runtime_helpers, runtime_helpers
from . import runtime_projection_helpers_runtime as projection_helpers_runtime
from .client import MCPClient, MCPConnectionResult
from .models import (
    McpRuntimeSnapshot,
)
from .remote_calls import call_projected_mcp_tool
from .resource_projection import (
    list_projected_mcp_resources,
    project_mcp_resource_provider_specs,
)
from .runtime_commands import (
    execute_resource_command,
    resource_command_specs,
    resource_tool_specs,
)
from .runtime_facade_helpers import (
    client_config_from_resolved_server,
)
from .runtime_support import ResolvedMcpServer
from .tool_projection import project_mcp_provider_tool_specs, project_mcp_tool_descriptors

PluginManagerGetter = Callable[[], Any]
RuntimePolicyGetter = Callable[[], Any]


class McpRuntimeFacade:
    def __init__(
        self,
        *,
        plugin_manager_getter: PluginManagerGetter,
        runtime_policy_getter: RuntimePolicyGetter | None = None,
    ) -> None:
        self._plugin_manager_getter = plugin_manager_getter
        self._runtime_policy_getter = runtime_policy_getter or (lambda: None)
        self._client = MCPClient()
        self._enabled_state: dict[str, bool] = {}
        self._runtime_dynamic: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> McpRuntimeFacade:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def snapshot(self) -> McpRuntimeSnapshot:
        _, snapshot, _, _ = self._refresh_state()
        return snapshot

    def snapshot_payload(self) -> dict[str, Any]:
        payload, snapshot, blocked, _ = self._refresh_state()
        payload["blocked"] = blocked
        payload["snapshot"] = snapshot.to_dict()
        payload["projected_tool_contracts"] = projection_helpers_runtime.projected_tool_contracts(
            payload,
            project_tool_descriptors_fn=project_mcp_tool_descriptors,
        )
        return payload

    def list_status(self) -> dict[str, Any]:
        payload, snapshot, blocked, _ = self._refresh_state()
        return {
            "servers": self.server_entries(),
            "projection_state": snapshot.projection_state.value,
            "blocked": blocked,
            "generated_at": snapshot.generated_at,
            "connections": dict(payload.get("connections") or {}),
        }

    def server_entries(self) -> list[dict[str, Any]]:
        _, _, _, entries = self._refresh_state()
        return [dict(item) for item in entries]

    def server_entries_map(self) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("name") or ""): dict(item)
            for item in self.server_entries()
            if str(item.get("name") or "").strip()
        }

    def inspect(self, server_name: str) -> dict[str, Any]:
        key = str(server_name or "").strip()
        if not key:
            raise ValueError("server name is required")
        for item in self.server_entries():
            if str(item.get("name") or "").strip() == key:
                return item
        raise ValueError(f"unknown mcp server: {key}")

    def enable(self, target: str) -> dict[str, Any]:
        return self._toggle_enabled(target, enabled=True)

    def disable(self, target: str) -> dict[str, Any]:
        return self._toggle_enabled(target, enabled=False)

    def reconnect(self, target: str) -> dict[str, Any]:
        names = self._target_names(target)
        if not names:
            raise ValueError("unknown mcp server target")
        if target.strip().lower() == "all":
            self._client.clear_cache()
        else:
            for name in names:
                self._client.invalidate(name)
        entries = self.server_entries()
        return {
            "status": "ok",
            "target": target,
            "servers": [item for item in entries if item.get("name") in names],
        }

    def list_resources(self, *, server_name: str | None = None) -> list[dict[str, Any]]:
        payload, _, _, _ = self._refresh_state()
        return list_projected_mcp_resources(payload, server_name=server_name)

    def list_channel_messages(self, server_name: str | None = None) -> list[dict[str, Any]]:
        return runtime_facade_runtime_helpers.list_channel_messages(self, server_name=server_name)

    def list_permission_requests(self, server_name: str | None = None) -> list[dict[str, Any]]:
        return runtime_facade_runtime_helpers.list_permission_requests(
            self, server_name=server_name
        )

    def respond_permission_request(
        self,
        server_name: str,
        request_id: str,
        approved: bool,
        reason: str = "",
    ) -> dict[str, Any]:
        return runtime_facade_runtime_helpers.respond_permission_request(
            self,
            server_name=server_name,
            request_id=request_id,
            approved=approved,
            reason=reason,
        )

    def respond_permission(
        self,
        *,
        server_name: str,
        request_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self.respond_permission_request(
            server_name=server_name,
            request_id=request_id,
            approved=approved,
            reason=str(reason or ""),
        )

    def permission_respond(
        self,
        server_name: str,
        request_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self.respond_permission_request(
            server_name=server_name,
            request_id=request_id,
            approved=approved,
            reason=str(reason or ""),
        )

    def respond_to_permission(
        self,
        server_name: str,
        request_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self.respond_permission_request(
            server_name=server_name,
            request_id=request_id,
            approved=approved,
            reason=str(reason or ""),
        )

    def read_resource(self, *, server_name: str, uri: str) -> dict[str, Any]:
        return runtime_facade_runtime_helpers.read_resource(self, server_name=server_name, uri=uri)

    def provider_tool_specs(self) -> list[dict[str, Any]]:
        payload, _, _, _ = self._refresh_state()
        return [
            *project_mcp_provider_tool_specs(payload),
            *project_mcp_resource_provider_specs(payload),
        ]

    def projected_tool_contracts(self) -> list[dict[str, Any]]:
        payload, _, _, _ = self._refresh_state()
        return projection_helpers_runtime.projected_tool_contracts(
            payload,
            project_tool_descriptors_fn=project_mcp_tool_descriptors,
        )

    def projected_tool_approval_request(
        self,
        *,
        projected_name: str,
        arguments: Mapping[str, Any] | None = None,
        requested_by: str = "mcp.runtime",
        approval_summary: str = "",
        approval_reason: str = "",
    ) -> dict[str, Any]:
        payload, _, _, _ = self._refresh_state()
        target_name = str(projected_name or "").strip()
        descriptor_map = projection_helpers_runtime.projected_tool_contract_map(
            payload,
            project_tool_descriptors_fn=project_mcp_tool_descriptors,
        )
        contract = descriptor_map.get(target_name)
        if contract is None:
            raise ValueError(f"unknown projected mcp tool: {target_name}")
        return projection_helpers_runtime.projected_tool_approval_request_payload(
            contract,
            arguments=arguments,
            requested_by=requested_by,
            approval_summary=approval_summary,
            approval_reason=approval_reason,
        )

    def tool_specs(self) -> list[dict[str, Any]]:
        payload, _, _, _ = self._refresh_state()
        return resource_tool_specs(payload)

    def command_specs(self) -> list[dict[str, str]]:
        payload, _, _, _ = self._refresh_state()
        return resource_command_specs(payload)

    def execute_command(
        self, name: str, arg_text: str, runtime: Any
    ) -> tuple[str, list[ToolEvent]] | None:
        return execute_resource_command(
            name=name,
            arg_text=arg_text,
            runtime=runtime,
            list_resources_fn=self.list_resources,
            read_resource_fn=self.read_resource,
        )

    def capability_mcp_servers(self) -> dict[str, dict[str, Any]]:
        return self.server_entries_map()

    def call_projected_tool(
        self, *, projected_name: str, arguments: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        payload, _, _, _ = self._refresh_state()
        started = time.perf_counter()
        result = call_projected_mcp_tool(
            payload=payload,
            projected_name=projected_name,
            arguments=arguments,
            connection_lookup=self._client.get_cached_connection_by_name,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        descriptor_map = projection_helpers_runtime.projected_tool_contract_map(
            payload,
            project_tool_descriptors_fn=project_mcp_tool_descriptors,
        )
        contract = descriptor_map.get(str(projected_name or "").strip())
        if contract is not None:
            projection_helpers_runtime.apply_projected_tool_call_projection(
                result,
                contract=contract,
                latency_ms=latency_ms,
            )
        return result

    def set_runtime_dynamic(self, name: str, config: Mapping[str, Any] | None) -> None:
        key = str(name or "").strip()
        if not key:
            raise ValueError("server name is required")
        if not isinstance(config, Mapping):
            self._runtime_dynamic.pop(key, None)
            return
        self._runtime_dynamic[key] = dict(config)

    def _toggle_enabled(self, target: str, *, enabled: bool) -> dict[str, Any]:
        names = self._target_names(target)
        if not names:
            raise ValueError("unknown mcp server target")
        for name in names:
            self._enabled_state[name] = enabled
            if not enabled:
                self._client.invalidate(name)
        entries = self.server_entries()
        return runtime_helpers.toggle_enabled_payload(
            target=target,
            enabled=enabled,
            names=names,
            entries=entries,
        )

    def _target_names(self, target: str) -> list[str]:
        return runtime_helpers.target_names(target, self.server_entries())

    def _refresh_state(
        self,
    ) -> tuple[dict[str, Any], McpRuntimeSnapshot, list[dict[str, Any]], list[dict[str, Any]]]:
        return runtime_facade_runtime_helpers.refresh_state(self)

    def _policy_payload(self) -> dict[str, Any] | None:
        runtime_policy = self._runtime_policy()
        if runtime_policy is None:
            return None
        return runtime_helpers.build_policy_payload(
            self._runtime_policy_value,
            self._gate_enabled,
        )

    def _runtime_policy(self) -> Any:
        return self._runtime_policy_getter()

    def _runtime_policy_value(self, key: str, default: Any = None) -> Any:
        return runtime_helpers.runtime_policy_value(self._runtime_policy(), key, default)

    def _gate_enabled(self, key: str) -> bool:
        raw = self._runtime_policy_value(key, False)
        return runtime_helpers.gate_enabled(raw)

    def _resolve_client_callable(self, names: tuple[str, ...]) -> Callable[..., Any] | None:
        return runtime_helpers.resolve_client_callable(self._client, names)

    @staticmethod
    def _call_client_list_fn(fn: Callable[..., Any], server_name: str) -> Any:
        return runtime_helpers.call_client_list_fn(fn, server_name)

    @staticmethod
    def _call_client_respond_fn(
        fn: Callable[..., Any],
        *,
        server_name: str,
        request_id: str,
        approved: bool,
        reason: str,
    ) -> Any:
        return runtime_helpers.call_client_respond_fn(
            fn,
            server_name=server_name,
            request_id=request_id,
            approved=approved,
            reason=reason,
        )

    @staticmethod
    def _normalize_notification_row(item: Any, *, server_name: str) -> dict[str, Any] | None:
        return runtime_helpers.normalize_notification_row(item, server_name=server_name)

    @staticmethod
    def _selected_server_names(
        *, entries: list[dict[str, Any]], server_name: str | None
    ) -> list[str]:
        return runtime_helpers.selected_server_names(entries=entries, server_name=server_name)

    @staticmethod
    def _normalize_optional_server_name(server_name: str | None) -> str | None:
        return runtime_helpers.normalize_optional_server_name(server_name)

    @staticmethod
    def _normalize_required_server_name(server_name: str) -> str:
        return runtime_helpers.normalize_required_server_name(server_name)

    def _connection_results(
        self, resolved: list[ResolvedMcpServer]
    ) -> dict[str, MCPConnectionResult]:
        configs = {item.name: client_config_from_resolved_server(item) for item in resolved}
        return self._client.connect_many(configs)
