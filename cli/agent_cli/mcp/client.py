from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from . import client_runtime_helpers
from .client_helpers import (
    DESCRIPTOR_KINDS,
    MCPConnectionHandle,
    MCPConnectionResult,
    MCPConnectionStatus,
    MCPServerConfig,
    _DescriptorCache,
    _RetryState,
    build_cache_key,
    consume_list_changed_notifications,
    drain_notification_cache,
    is_channel_message_method,
    is_permission_request_method,
    is_stale_handle,
    notification_method,
    notification_payload,
    notification_server_names,
    remote_descriptors,
    status_from_transport_error,
)
from .transports import MCPTransportError, connect_transport


class MCPClient:
    def __init__(self) -> None:
        self._cache: dict[str, MCPConnectionHandle] = {}
        self._retry_state: dict[str, _RetryState] = {}
        self._descriptor_cache: dict[str, _DescriptorCache] = {}
        self._channel_message_cache: dict[str, list[dict[str, Any]]] = {}
        self._permission_request_cache: dict[str, list[dict[str, Any]]] = {}
        self._base_backoff_sec = 0.5
        self._max_backoff_sec = 8.0
        self._max_retry_attempts = 5

    def close(self) -> None:
        self.clear_cache()

    def __enter__(self) -> MCPClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def cache_size(self) -> int:
        return len(self._cache)

    def clear_cache(self) -> None:
        for handle in list(self._cache.values()):
            self._close_handle(handle)
        self._cache.clear()
        self._retry_state.clear()
        self._descriptor_cache.clear()
        self._channel_message_cache.clear()
        self._permission_request_cache.clear()

    def invalidate(self, name: str) -> None:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            return
        for key in [
            cache_key for cache_key in self._cache if cache_key.startswith(f"{normalized_name}|")
        ]:
            handle = self._cache.pop(key, None)
            if handle is not None:
                self._close_handle(handle)
        self._retry_state.pop(normalized_name, None)
        self._descriptor_cache.pop(normalized_name, None)
        self._channel_message_cache.pop(normalized_name, None)
        self._permission_request_cache.pop(normalized_name, None)

    def get_cached_connection(self, config: MCPServerConfig) -> MCPConnectionHandle | None:
        return self._cache.get(self._cache_key(config))

    def get_cached_connection_by_name(self, name: str) -> MCPConnectionHandle | None:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            return None
        for handle in self._cache.values():
            if handle.name == normalized_name:
                return handle
        return None

    def reconnect(self, config: MCPServerConfig) -> MCPConnectionResult:
        self.invalidate(config.name)
        return self.connect(config)

    def connect_many(
        self, configs: Mapping[str, MCPServerConfig]
    ) -> dict[str, MCPConnectionResult]:
        results: dict[str, MCPConnectionResult] = {}
        for server_name, config in configs.items():
            results[server_name] = self.connect(config)
        return results

    def prune_stale_servers(self, active_names: set[str]) -> None:
        client_runtime_helpers.prune_stale_servers(
            active_names=active_names,
            cache=self._cache,
            close_handle=self._close_handle,
            retry_state=self._retry_state,
            descriptor_cache=self._descriptor_cache,
            channel_message_cache=self._channel_message_cache,
            permission_request_cache=self._permission_request_cache,
        )

    def drain_channel_messages(self, *, name: str) -> list[dict[str, Any]]:
        return self._drain_notification_cache(name=name, cache=self._channel_message_cache)

    def drain_permission_requests(self, *, name: str) -> list[dict[str, Any]]:
        return self._drain_notification_cache(name=name, cache=self._permission_request_cache)

    def list_channel_messages(self, *, server_name: str | None = None) -> list[dict[str, Any]]:
        names = self._notification_server_names(server_name)
        rows: list[dict[str, Any]] = []
        for name in names:
            for item in self.drain_channel_messages(name=name):
                row = self._notification_payload(item)
                params = row.get("params")
                if isinstance(params, Mapping):
                    row.setdefault(
                        "server", str(params.get("server") or params.get("server_name") or name)
                    )
                else:
                    row.setdefault("server", name)
                rows.append(row)
        return rows

    def list_permission_requests(self, *, server_name: str | None = None) -> list[dict[str, Any]]:
        names = self._notification_server_names(server_name)
        rows: list[dict[str, Any]] = []
        for name in names:
            for item in self.drain_permission_requests(name=name):
                row = self._notification_payload(item)
                params = row.get("params")
                if isinstance(params, Mapping):
                    row.setdefault(
                        "server", str(params.get("server") or params.get("server_name") or name)
                    )
                else:
                    row.setdefault("server", name)
                rows.append(row)
        return rows

    def respond_permission_request(
        self,
        *,
        server_name: str,
        request_id: str,
        approved: bool,
        reason: str = "",
    ) -> dict[str, Any]:
        return client_runtime_helpers.respond_permission_request(
            server_name=server_name,
            request_id=request_id,
            approved=approved,
            reason=reason,
            get_cached_connection_by_name=self.get_cached_connection_by_name,
        )

    def remote_tools(self, *, name: str, session: Any) -> list[dict[str, Any]]:
        return self._remote_descriptors(
            name=name, session=session, kind="tools", method_name="tools_list"
        )

    def remote_prompts(self, *, name: str, session: Any) -> list[dict[str, Any]]:
        return self._remote_descriptors(
            name=name, session=session, kind="prompts", method_name="prompts_list"
        )

    def remote_resources(self, *, name: str, session: Any) -> list[dict[str, Any]]:
        return self._remote_descriptors(
            name=name, session=session, kind="resources", method_name="resources_list"
        )

    def invalidate_remote_descriptors(self, *, name: str, kinds: set[str] | None = None) -> None:
        server_name = str(name or "").strip()
        if not server_name:
            return
        cache = self._descriptor_cache.setdefault(server_name, _DescriptorCache())
        if kinds is None:
            cache.dirty.update(DESCRIPTOR_KINDS)
            return
        for kind in kinds:
            if kind in DESCRIPTOR_KINDS:
                cache.dirty.add(kind)

    def connect(self, config: MCPServerConfig) -> MCPConnectionResult:
        server_name = str(config.name or "").strip()
        if not config.enabled or not config.transport.enabled:
            self._retry_state.pop(server_name, None)
            return MCPConnectionResult(name=config.name, status="disabled")

        cache_key = self._cache_key(config)
        cached = self._cache.get(cache_key)
        if cached is not None:
            if self._is_stale_handle(cached):
                self.invalidate(cached.name)
            else:
                self._consume_list_changed(server_name, cached.session)
                return MCPConnectionResult(
                    name=config.name, status="connected", handle=cached, from_cache=True
                )

        if config.transport.transport != "stdio":
            waiting = self._retry_waiting(server_name)
            if waiting is not None:
                return MCPConnectionResult(
                    name=config.name,
                    status="failed",
                    error_code="retry-backoff",
                    error=f"retry scheduled in {waiting:.2f}s",
                    retry_attempt=self._retry_state.get(server_name, _RetryState()).attempt,
                    retry_in_sec=waiting,
                )

        try:
            connection = connect_transport(config.transport)
        except MCPTransportError as exc:
            status = _status_from_transport_error(exc)
            attempt = 0
            retry_in_sec = 0.0
            if status == "failed" and config.transport.transport != "stdio":
                attempt, retry_in_sec = self._record_connect_failure(server_name)
            elif status != "failed":
                self._retry_state.pop(server_name, None)
            return MCPConnectionResult(
                name=config.name,
                status=status,
                error_code=exc.error_code,
                error=str(exc),
                retry_attempt=attempt,
                retry_in_sec=retry_in_sec,
            )

        self._retry_state.pop(server_name, None)
        handle = MCPConnectionHandle(
            name=config.name,
            fingerprint=cache_key,
            connected_at=time.time(),
            transport=connection,
            session=connection.session,
            server_info=dict(connection.server_info),
            capabilities=dict(connection.capabilities),
            instructions=str(connection.instructions or ""),
        )
        self._cache[cache_key] = handle
        self._consume_list_changed(server_name, handle.session)
        return MCPConnectionResult(name=config.name, status="connected", handle=handle)

    def _remote_descriptors(
        self, *, name: str, session: Any, kind: str, method_name: str
    ) -> list[dict[str, Any]]:
        return remote_descriptors(
            name=name,
            session=session,
            kind=kind,
            method_name=method_name,
            descriptor_cache=self._descriptor_cache,
            consume_list_changed=self._consume_list_changed,
        )

    def _consume_list_changed(self, server_name: str, session: Any) -> None:
        consume_list_changed_notifications(
            server_name=server_name,
            session=session,
            channel_message_cache=self._channel_message_cache,
            permission_request_cache=self._permission_request_cache,
            invalidate_remote_descriptors=self.invalidate_remote_descriptors,
            resolve_method=self._notification_method,
            resolve_payload=self._notification_payload,
            is_channel_message=self._is_channel_message_method,
            is_permission_request=self._is_permission_request_method,
        )

    @staticmethod
    def _notification_method(notification: Any) -> str:
        return notification_method(notification)

    @staticmethod
    def _notification_payload(notification: Any) -> dict[str, Any]:
        return notification_payload(notification)

    @staticmethod
    def _is_channel_message_method(method: str) -> bool:
        return is_channel_message_method(method)

    @staticmethod
    def _is_permission_request_method(method: str) -> bool:
        return is_permission_request_method(method)

    def _drain_notification_cache(
        self,
        *,
        name: str,
        cache: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        return drain_notification_cache(
            name=name,
            cache=cache,
            get_cached_connection_by_name=self.get_cached_connection_by_name,
            consume_list_changed=self._consume_list_changed,
            resolve_payload=self._notification_payload,
        )

    def _notification_server_names(self, server_name: str | None) -> list[str]:
        return notification_server_names(
            server_name=server_name,
            handles=self._cache,
            channel_message_cache=self._channel_message_cache,
            permission_request_cache=self._permission_request_cache,
        )

    def _retry_waiting(self, server_name: str) -> float | None:
        return client_runtime_helpers.retry_waiting(self._retry_state, server_name=server_name)

    def _record_connect_failure(self, server_name: str) -> tuple[int, float]:
        return client_runtime_helpers.record_connect_failure(
            self._retry_state,
            server_name=server_name,
            max_retry_attempts=self._max_retry_attempts,
            base_backoff_sec=self._base_backoff_sec,
            max_backoff_sec=self._max_backoff_sec,
        )

    @staticmethod
    def _is_stale_handle(handle: MCPConnectionHandle) -> bool:
        return is_stale_handle(handle)

    def _cache_key(self, config: MCPServerConfig) -> str:
        return build_cache_key(config)

    @staticmethod
    def _close_handle(handle: MCPConnectionHandle) -> None:
        try:
            handle.close()
        except Exception:
            pass


def _status_from_transport_error(exc: MCPTransportError) -> MCPConnectionStatus:
    return status_from_transport_error(exc)
