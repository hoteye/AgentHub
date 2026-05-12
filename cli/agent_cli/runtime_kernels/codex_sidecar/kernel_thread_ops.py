from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.kernel_params import _require_thread_id
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject
from cli.agent_cli.runtime_kernels.errors import RuntimeKernelSessionError


class _CodexSidecarKernelThreadOps:
    def read_thread(self, thread_id: str, *, include_turns: bool = True) -> JsonObject:
        self._ensure_initialized()
        return self._client.request(
            "thread/read",
            {
                "threadId": _require_thread_id(thread_id),
                "includeTurns": bool(include_turns),
            },
        )

    def list_threads(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        sort_key: str | None = None,
        sort_direction: str | None = None,
        model_providers: list[str] | None = None,
        source_kinds: list[str] | None = None,
        archived: bool | None = None,
        cwd: str | list[str] | None = None,
        use_state_db_only: bool | None = None,
        search_term: str | None = None,
    ) -> JsonObject:
        self._ensure_initialized()
        params: JsonObject = {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = int(limit)
        if sort_key is not None:
            params["sortKey"] = str(sort_key)
        if sort_direction is not None:
            params["sortDirection"] = str(sort_direction)
        if model_providers is not None:
            params["modelProviders"] = [str(item) for item in model_providers]
        if source_kinds is not None:
            params["sourceKinds"] = [str(item) for item in source_kinds]
        if archived is not None:
            params["archived"] = bool(archived)
        if cwd is not None:
            params["cwd"] = [str(item) for item in cwd] if isinstance(cwd, list) else str(cwd)
        if use_state_db_only is not None:
            params["useStateDbOnly"] = bool(use_state_db_only)
        if search_term is not None:
            params["searchTerm"] = str(search_term)
        return self._client.request("thread/list", params)

    def list_loaded_threads(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> JsonObject:
        self._ensure_initialized()
        params: JsonObject = {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = int(limit)
        return self._client.request("thread/loaded/list", params)

    def archive_thread(self, thread_id: str) -> JsonObject:
        self._ensure_initialized()
        return self._client.request(
            "thread/archive",
            {"threadId": _require_thread_id(thread_id)},
        )

    def unarchive_thread(self, thread_id: str) -> JsonObject:
        self._ensure_initialized()
        return self._client.request(
            "thread/unarchive",
            {"threadId": _require_thread_id(thread_id)},
        )

    def rollback_thread(self, thread_id: str, *, num_turns: int = 1) -> JsonObject:
        self._ensure_initialized()
        turns = int(num_turns)
        if turns < 1:
            raise RuntimeKernelSessionError("codex sidecar rollback requires num_turns >= 1")
        return self._client.request(
            "thread/rollback",
            {
                "threadId": _require_thread_id(thread_id),
                "numTurns": turns,
            },
        )

    def compact_thread(self, thread_id: str) -> JsonObject:
        self._ensure_initialized()
        return self._client.request(
            "thread/compact/start",
            {"threadId": _require_thread_id(thread_id)},
        )

    def set_thread_name(self, thread_id: str, name: str) -> JsonObject:
        self._ensure_initialized()
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise RuntimeKernelSessionError("codex sidecar thread name must not be empty")
        return self._client.request(
            "thread/name/set",
            {
                "threadId": _require_thread_id(thread_id),
                "name": normalized_name,
            },
        )

    def update_thread_metadata(self, thread_id: str, metadata: Mapping[str, Any]) -> JsonObject:
        self._ensure_initialized()
        if not isinstance(metadata, Mapping):
            raise RuntimeKernelSessionError("codex sidecar thread metadata must be a mapping")
        params: JsonObject = {
            "threadId": _require_thread_id(thread_id),
            **dict(metadata),
        }
        return self._client.request("thread/metadata/update", params)
