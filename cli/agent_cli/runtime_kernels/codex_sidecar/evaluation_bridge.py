from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CodexSidecarEvaluationBridge:
    kernel: Any
    thread_id: str = ""
    allowed_mcp_tools: set[str] = field(default_factory=set)

    def list_mcp_servers(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        detail: str | None = None,
    ) -> JsonObject:
        return self.kernel.list_mcp_server_status(
            cursor=cursor,
            limit=limit,
            detail=detail,
        )

    def list_skills(
        self,
        *,
        cwds: list[str] | None = None,
        force_reload: bool | None = None,
    ) -> JsonObject:
        return self.kernel.list_skills(cwds=cwds, force_reload=force_reload)

    def list_plugins(self, *, cwds: list[str] | None = None) -> JsonObject:
        return self.kernel.list_plugins(cwds=cwds)

    def read_plugin(
        self,
        plugin_name: str,
        *,
        marketplace_path: str | None = None,
        remote_marketplace_name: str | None = None,
    ) -> JsonObject:
        return self.kernel.read_plugin(
            plugin_name,
            marketplace_path=marketplace_path,
            remote_marketplace_name=remote_marketplace_name,
        )

    def read_mcp_resource(
        self,
        *,
        server: str,
        uri: str,
        thread_id: str | None = None,
    ) -> JsonObject:
        return self.kernel.read_mcp_resource(
            server=server,
            uri=uri,
            thread_id=thread_id or self.thread_id or None,
        )

    def call_mcp_tool(
        self,
        *,
        server: str,
        tool: str,
        arguments: JsonObject | None = None,
        meta: JsonObject | None = None,
        thread_id: str | None = None,
    ) -> JsonObject:
        key = f"{server}/{tool}"
        allowlist = self._allowlist()
        if key not in allowlist:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Codex sidecar MCP tool is not allowlisted: {key}",
                    }
                ],
                "isError": True,
                "_meta": {"blockedBy": "agenthub_allowlist", "tool": key},
            }
        return self.kernel.call_mcp_tool(
            server=server,
            tool=tool,
            arguments=arguments,
            meta=meta,
            thread_id=thread_id or self.thread_id or None,
        )

    def namespace_summary(self) -> dict[str, list[str]]:
        mcp_servers = []
        skills = []
        plugins = []
        try:
            mcp_servers = [
                f"mcp:{item.get('name')}"
                for item in list(self.list_mcp_servers().get("data") or [])
                if isinstance(item, dict) and item.get("name")
            ]
        except Exception:
            logger.debug("codex sidecar MCP namespace summary failed", exc_info=True)
            mcp_servers = []
        try:
            for entry in list(self.list_skills().get("data") or []):
                for skill in list(dict(entry).get("skills") or []):
                    if isinstance(skill, dict) and skill.get("name"):
                        skills.append(f"codex:skill:{skill.get('name')}")
        except Exception:
            logger.debug("codex sidecar skills namespace summary failed", exc_info=True)
            skills = []
        try:
            for marketplace in list(self.list_plugins().get("marketplaces") or []):
                marketplace_name = str(dict(marketplace).get("name") or "").strip()
                for plugin in list(dict(marketplace).get("plugins") or []):
                    if isinstance(plugin, dict) and plugin.get("name"):
                        plugins.append(f"codex:{marketplace_name}/{plugin.get('name')}")
        except Exception:
            logger.debug("codex sidecar plugins namespace summary failed", exc_info=True)
            plugins = []
        return {
            "mcp_servers": mcp_servers,
            "skills": skills,
            "plugins": plugins,
        }

    def allow_mcp_tool(self, server: str, tool: str) -> None:
        self._shared_allowlist().add(f"{server}/{tool}")

    def _allowlist(self) -> set[str]:
        return {*self.allowed_mcp_tools, *self._shared_allowlist()}

    def _shared_allowlist(self) -> set[str]:
        shared = getattr(self.kernel, "mcp_tool_allowlist", None)
        if not isinstance(shared, set):
            return self.allowed_mcp_tools
        return shared
