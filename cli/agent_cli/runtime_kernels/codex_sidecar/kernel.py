from __future__ import annotations

import threading
from collections.abc import Mapping
from pathlib import Path

from cli.agent_cli.runtime_kernels.base import (
    ForkSessionRequest,
    KernelEngine,
    KernelSession,
    ResumeSessionRequest,
    StartSessionRequest,
    StartTurnRequest,
    TurnHandle,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.artifact import (
    CodexSidecarArtifact,
    CodexSidecarArtifactConfig,
    codex_sidecar_external_binary_allowed,
    resolve_codex_sidecar_artifact,
    resolve_codex_sidecar_test_binary,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.client import CodexSidecarClient
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection import (
    CodexSidecarProjectedConfig,
    merge_sidecar_projected_env,
    prepare_codex_sidecar_projected_config,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.kernel_env import (
    _sidecar_inherited_remove_env_keys,
    _sidecar_runtime_env,
    _sidecar_scrubbed_env_keys,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.kernel_params import (
    _require_absolute_path,
    _require_text,
    _thread_fork_params,
    _thread_resume_params,
    _thread_start_params,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.kernel_sessions import (
    _session_from_thread_result,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.kernel_thread_ops import (
    _CodexSidecarKernelThreadOps,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.kernel_turns import (
    _turn_id_from_result,
    _turn_input_items,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject
from cli.agent_cli.runtime_kernels.codex_sidecar.supervisor import CodexSidecarSupervisor
from cli.agent_cli.runtime_kernels.errors import RuntimeKernelSessionError


class CodexSidecarKernel(_CodexSidecarKernelThreadOps):
    engine: KernelEngine = "codex_sidecar"

    def __init__(
        self,
        client: CodexSidecarClient | None = None,
        *,
        codex_bin: str | Path | None = None,
        artifact_config: CodexSidecarArtifactConfig | None = None,
        extra_env: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
        request_timeout: float = 30.0,
    ) -> None:
        self._artifact: CodexSidecarArtifact | None = None
        self._projected_config: CodexSidecarProjectedConfig | None = None
        if client is None:
            if codex_bin is not None:
                if not codex_sidecar_external_binary_allowed():
                    raise RuntimeKernelSessionError(
                        "external codex sidecar binary is disabled in release builds"
                    )
                resolved_codex_bin = Path(codex_bin)
            else:
                resolved_test_bin = resolve_codex_sidecar_test_binary()
                if resolved_test_bin is not None:
                    resolved_codex_bin = resolved_test_bin
                else:
                    try:
                        self._artifact = resolve_codex_sidecar_artifact(artifact_config)
                    except Exception as exc:
                        raise RuntimeKernelSessionError(str(exc)) from exc
                    resolved_codex_bin = self._artifact.path
            projection_env = {str(key): str(value) for key, value in dict(extra_env or {}).items()}
            self._projected_config = prepare_codex_sidecar_projected_config(
                cwd=cwd,
                env=projection_env,
            )
            projected_env = merge_sidecar_projected_env(
                base_env=extra_env,
                projection=self._projected_config,
            )
            scrubbed_env_keys = _sidecar_scrubbed_env_keys(self._projected_config)
            inherited_remove_env_keys = _sidecar_inherited_remove_env_keys(scrubbed_env_keys)
            resolved_extra_env = _sidecar_runtime_env(
                artifact=self._artifact,
                extra_env=projected_env,
                scrubbed_env_keys=scrubbed_env_keys,
            )
            client = CodexSidecarClient(
                CodexSidecarSupervisor(
                    codex_bin=resolved_codex_bin,
                    extra_env=resolved_extra_env,
                    remove_env_keys=inherited_remove_env_keys,
                ),
                request_timeout=request_timeout,
            )
        self._client = client
        self._initialized = False
        self._init_lock = threading.Lock()
        self._sessions: dict[str, KernelSession] = {}
        self.mcp_tool_allowlist: set[str] = set()

    @property
    def client(self) -> CodexSidecarClient:
        return self._client

    @property
    def artifact(self) -> CodexSidecarArtifact | None:
        return self._artifact

    @property
    def projected_config(self) -> CodexSidecarProjectedConfig | None:
        return self._projected_config

    async def start_session(self, request: StartSessionRequest) -> KernelSession:
        self._ensure_initialized()
        result = self._client.request("thread/start", _thread_start_params(request))
        session = _session_from_thread_result(result, metadata=request.metadata)
        self._sessions[session.session_id] = session
        return session

    async def resume_session(self, request: ResumeSessionRequest) -> KernelSession:
        self._ensure_initialized()
        result = self._client.request("thread/resume", _thread_resume_params(request))
        session = _session_from_thread_result(result, metadata=request.metadata)
        self._sessions[session.session_id] = session
        return session

    async def fork_session(self, request: ForkSessionRequest) -> KernelSession:
        self._ensure_initialized()
        result = self._client.request("thread/fork", _thread_fork_params(request))
        session = _session_from_thread_result(result, metadata=request.metadata)
        self._sessions[session.session_id] = session
        return session

    async def start_turn(self, request: StartTurnRequest) -> TurnHandle:
        self._ensure_initialized()
        session = self._sessions.get(request.session_id)
        if session is None:
            raise RuntimeKernelSessionError(f"runtime session not found: {request.session_id}")
        result = self._client.request(
            "turn/start",
            {
                "threadId": session.thread_id,
                "input": _turn_input_items(request),
            },
        )
        turn_id = _turn_id_from_result(result)
        return TurnHandle(
            session_id=request.session_id,
            turn_id=turn_id,
            metadata={**dict(request.metadata or {}), "raw_result": result},
        )

    async def cancel_turn(self, session_id: str, turn_id: str | None = None) -> None:
        self.cancel_turn_sync(session_id, turn_id)

    def cancel_turn_sync(self, session_id: str, turn_id: str | None = None) -> None:
        session = self._sessions.get(str(session_id or "").strip())
        if session is None:
            raise RuntimeKernelSessionError(f"runtime session not found: {session_id}")
        normalized_turn_id = str(turn_id or "").strip()
        if not normalized_turn_id:
            raise RuntimeKernelSessionError("codex sidecar cancel requires turn_id")
        self._client.request(
            "turn/interrupt",
            {
                "threadId": session.thread_id,
                "turnId": normalized_turn_id,
            },
        )

    async def steer_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        text: str = "",
        input_items: list[JsonObject] | None = None,
    ) -> JsonObject:
        return self.steer_turn_sync(
            session_id=session_id,
            turn_id=turn_id,
            text=text,
            input_items=input_items,
        )

    def steer_turn_sync(
        self,
        *,
        session_id: str,
        turn_id: str,
        text: str = "",
        input_items: list[JsonObject] | None = None,
    ) -> JsonObject:
        session = self._sessions.get(str(session_id or "").strip())
        if session is None:
            raise RuntimeKernelSessionError(f"runtime session not found: {session_id}")
        normalized_turn_id = str(turn_id or "").strip()
        if not normalized_turn_id:
            raise RuntimeKernelSessionError("codex sidecar steer requires turn_id")
        items = [dict(item) for item in list(input_items or []) if isinstance(item, dict)]
        if not items:
            normalized_text = str(text or "").strip()
            if not normalized_text:
                raise RuntimeKernelSessionError("codex sidecar steer requires input")
            items = [
                {
                    "type": "text",
                    "text": normalized_text,
                    "textElements": [],
                }
            ]
        return self._client.request(
            "turn/steer",
            {
                "threadId": session.thread_id,
                "input": items,
                "expectedTurnId": normalized_turn_id,
            },
        )

    def list_models(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        include_hidden: bool | None = None,
    ) -> JsonObject:
        self._ensure_initialized()
        params: JsonObject = {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = int(limit)
        if include_hidden is not None:
            params["includeHidden"] = bool(include_hidden)
        return self._client.request("model/list", params)

    def read_model_provider_capabilities(self) -> JsonObject:
        self._ensure_initialized()
        return self._client.request("modelProvider/capabilities/read", {})

    def fs_read_file(self, path: str) -> JsonObject:
        self._ensure_initialized()
        return self._client.request("fs/readFile", {"path": _require_absolute_path(path)})

    def fs_read_directory(self, path: str) -> JsonObject:
        self._ensure_initialized()
        return self._client.request("fs/readDirectory", {"path": _require_absolute_path(path)})

    def fs_get_metadata(self, path: str) -> JsonObject:
        self._ensure_initialized()
        return self._client.request("fs/getMetadata", {"path": _require_absolute_path(path)})

    def list_mcp_server_status(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        detail: str | None = None,
    ) -> JsonObject:
        self._ensure_initialized()
        params: JsonObject = {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = int(limit)
        if detail is not None:
            params["detail"] = str(detail)
        return self._client.request("mcpServerStatus/list", params)

    def list_skills(
        self,
        *,
        cwds: list[str] | None = None,
        force_reload: bool | None = None,
    ) -> JsonObject:
        self._ensure_initialized()
        params: JsonObject = {}
        if cwds is not None:
            params["cwds"] = [str(item) for item in cwds]
        if force_reload is not None:
            params["forceReload"] = bool(force_reload)
        return self._client.request("skills/list", params)

    def list_plugins(self, *, cwds: list[str] | None = None) -> JsonObject:
        self._ensure_initialized()
        params: JsonObject = {}
        if cwds is not None:
            params["cwds"] = [str(item) for item in cwds]
        return self._client.request("plugin/list", params)

    def read_plugin(
        self,
        plugin_name: str,
        *,
        marketplace_path: str | None = None,
        remote_marketplace_name: str | None = None,
    ) -> JsonObject:
        self._ensure_initialized()
        normalized_name = str(plugin_name or "").strip()
        if not normalized_name:
            raise RuntimeKernelSessionError("codex sidecar plugin_name is required")
        params: JsonObject = {"pluginName": normalized_name}
        if marketplace_path:
            params["marketplacePath"] = _require_absolute_path(marketplace_path)
        if remote_marketplace_name:
            params["remoteMarketplaceName"] = str(remote_marketplace_name)
        return self._client.request("plugin/read", params)

    def read_mcp_resource(
        self,
        *,
        server: str,
        uri: str,
        thread_id: str | None = None,
    ) -> JsonObject:
        self._ensure_initialized()
        params: JsonObject = {
            "server": _require_text(server, "mcp server"),
            "uri": _require_text(uri, "mcp resource uri"),
        }
        if thread_id:
            params["threadId"] = str(thread_id)
        return self._client.request("mcpServer/resource/read", params)

    def call_mcp_tool(
        self,
        *,
        server: str,
        tool: str,
        arguments: JsonObject | None = None,
        meta: JsonObject | None = None,
        thread_id: str | None = None,
    ) -> JsonObject:
        self._ensure_initialized()
        params: JsonObject = {
            "server": _require_text(server, "mcp server"),
            "tool": _require_text(tool, "mcp tool"),
        }
        if thread_id:
            params["threadId"] = str(thread_id)
        if arguments is not None:
            params["arguments"] = dict(arguments)
        if meta is not None:
            params["_meta"] = dict(meta)
        return self._client.request("mcpServer/tool/call", params)

    async def close_session(self, session_id: str) -> None:
        self._sessions.pop(str(session_id or "").strip(), None)

    async def aclose(self) -> None:
        self._sessions.clear()
        self._client.close()
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self._client.initialize()
            self._initialized = True
