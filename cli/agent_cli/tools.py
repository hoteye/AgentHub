from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    browser_web_runtime,
    document_tools_runtime,
    file_tools_runtime,
    shell_tools_runtime,
    tool_registry_bootstrap_runtime,
    tool_registry_compat_runtime,
    tool_registry_runtime,
    tools_helper_runtime,
    web_registry_runtime,
)
from cli.agent_cli.tools_core.project_loader import (
    PROJECT_ROOT,
)
from cli.agent_cli.tools_core.registry import PluginBridge
from cli.agent_cli.tools_core.registry import (
    build_capabilities_payload as _build_capabilities_payload,
)

apply_patch_bridge_module = tools_helper_runtime.ApplyPatchBridgeCompat
file_tools_bridge_module = file_tools_runtime
load_browser_config = browser_web_runtime.load_browser_config
resolve_browser_profiles = browser_web_runtime.resolve_browser_profiles
create_browser_proxy_transport = browser_web_runtime.create_browser_proxy_transport
build_capabilities_payload = _build_capabilities_payload


def _find_project_root() -> Path:
    return tools_helper_runtime.find_tools_project_root(tools_dir=Path(__file__).resolve().parent)


def _json_safe(value: Any) -> Any:
    return tools_helper_runtime.json_safe_value(value)


def _load_project_tool_module(module_name: str):
    return tools_helper_runtime.load_project_tool(
        module_name,
        project_root=PROJECT_ROOT,
        tools_module_file=Path(__file__).resolve(),
    )


class ToolRegistry:
    def __init__(self) -> None:
        tool_registry_bootstrap_runtime.initialize_tool_registry_state(self)

    @property
    def _plugin_bridge(self) -> PluginBridge:
        return PluginBridge(self._plugin_manager)

    def _get_office_tools(self):
        self._office_tools = document_tools_runtime.get_office_tools(
            cached_tools=self._office_tools,
            load_project_tool_module=_load_project_tool_module,
        )
        return self._office_tools

    def _get_internal_policy_tools(self):
        self._internal_policy_tools = document_tools_runtime.get_internal_policy_tools(
            cached_tools=self._internal_policy_tools,
            load_project_tool_module=_load_project_tool_module,
        )
        return self._internal_policy_tools

    def _get_web_search_tools(self):
        self._web_search_tools = web_registry_runtime.get_web_search_tools(
            cached_tools=self._web_search_tools,
            load_project_tool_module=_load_project_tool_module,
            project_root=PROJECT_ROOT,
        )
        return self._web_search_tools

    @staticmethod
    def _event(name: str, ok: bool, summary: str, payload: dict[str, Any]) -> ToolEvent:
        return tool_registry_runtime.event(name, ok, summary, payload)

    @staticmethod
    def _compact_arguments(arguments: dict[str, Any] | None) -> dict[str, Any]:
        return tool_registry_runtime.compact_arguments(arguments)

    def _result_from_event(
        self,
        assistant_text: str,
        event: ToolEvent,
        *,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> CommandExecutionResult:
        return tool_registry_runtime.result_from_event(
            self,
            assistant_text,
            event,
            tool_name=tool_name,
            arguments=arguments,
        )

    @staticmethod
    def _call_structured_helper(
        target: Any, method_name: str, *args: Any, **kwargs: Any
    ) -> CommandExecutionResult | None:
        return tool_registry_runtime.call_structured_helper(target, method_name, *args, **kwargs)

    def _get_browser_client(self) -> Any | None:
        return web_registry_runtime.get_browser_client(self)

    def _profile_prefers_local_browser(self, *, profile: str | None) -> bool:
        return tool_registry_compat_runtime.profile_prefers_local_browser(
            self,
            profile=profile,
            load_browser_config=load_browser_config,
            resolve_browser_profiles=resolve_browser_profiles,
            create_browser_proxy_transport=create_browser_proxy_transport,
        )

    def _get_browser_executor(
        self, *, profile: str | None = None, transport: str | None = None
    ) -> Any | None:
        return tool_registry_compat_runtime.get_browser_executor(
            self,
            profile=profile,
            transport=transport,
            load_browser_config=load_browser_config,
            resolve_browser_profiles=resolve_browser_profiles,
            create_browser_proxy_transport=create_browser_proxy_transport,
        )

    def shell(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 60,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ToolEvent:
        return shell_tools_runtime.shell(
            self,
            command,
            cwd=cwd,
            timeout_sec=timeout_sec,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )

    def shell_result(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 60,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CommandExecutionResult:
        return shell_tools_runtime.shell_result(
            self,
            command,
            cwd=cwd,
            timeout_sec=timeout_sec,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )

    def shell_start(
        self,
        command: str,
        *,
        cwd: str | None = None,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        return shell_tools_runtime.shell_start(
            self,
            command,
            cwd=cwd,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
        )

    def shell_start_result(
        self,
        command: str,
        *,
        cwd: str | None = None,
        login: bool = True,
        tty: bool = False,
        shell: str | None = None,
        max_output_chars: int = 12000,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> CommandExecutionResult:
        return shell_tools_runtime.shell_start_result(
            self,
            command,
            cwd=cwd,
            login=login,
            tty=tty,
            shell=shell,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
        )

    def shell_write_stdin(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        allow_extended_empty_poll: bool = False,
        max_output_chars: int | None = None,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ToolEvent:
        return shell_tools_runtime.shell_write_stdin(
            self,
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            allow_extended_empty_poll=allow_extended_empty_poll,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )

    def shell_write_stdin_result(
        self,
        session_id: str,
        chars: str,
        *,
        yield_time_ms: int | float | None = None,
        allow_extended_empty_poll: bool = False,
        max_output_chars: int | None = None,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CommandExecutionResult:
        return shell_tools_runtime.shell_write_stdin_result(
            self,
            session_id,
            chars,
            yield_time_ms=yield_time_ms,
            allow_extended_empty_poll=allow_extended_empty_poll,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )

    def shell_terminate(
        self,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolEvent:
        return shell_tools_runtime.shell_terminate(
            self,
            session_id,
            on_activity=on_activity,
        )

    def shell_terminate_result(
        self,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> CommandExecutionResult:
        return shell_tools_runtime.shell_terminate_result(
            self,
            session_id,
            on_activity=on_activity,
        )

    def interrupt_shell_sessions(
        self,
        *,
        cancel_event: threading.Event | None,
        reason: str = "user_interrupt",
    ) -> dict[str, Any]:
        return shell_tools_runtime.interrupt_shell_sessions(
            self,
            cancel_event=cancel_event,
            reason=reason,
        )

    def shell_subscribe(
        self,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> ToolEvent:
        return shell_tools_runtime.shell_subscribe(
            self,
            session_id,
            on_activity=on_activity,
        )

    def shell_subscribe_result(
        self,
        session_id: str,
        *,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> CommandExecutionResult:
        return shell_tools_runtime.shell_subscribe_result(
            self,
            session_id,
            on_activity=on_activity,
        )


tool_registry_bootstrap_runtime.bind_tool_registry_runtime(
    ToolRegistry,
    capabilities_method=tool_registry_compat_runtime.make_capabilities_method(
        build_capabilities_payload_getter=lambda: build_capabilities_payload,
    ),
)
