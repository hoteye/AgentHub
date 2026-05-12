from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.agent_cli.host import plugin_capability_declaration as capability_decl
from cli.agent_cli.host.plugin_manifest import PluginManifest
from cli.agent_cli.host.plugin_types import LoadedPlugin


def test_normalize_plugin_capability_declarations_accepts_valid_v1_shape() -> None:
    result = capability_decl.normalize_plugin_capability_declarations(
        [
            {
                "capability_id": "demo.search",
                "kind": "provider_tool",
                "tool_name": "demo_search",
                "canonical_family": "web_search",
                "supported_profiles": ["codex_openai", "generic_chat", "generic_chat"],
                "default_visibility": "model_visible",
                "plugin_name": "demo_plugin",
            }
        ]
    )

    assert result.errors == ()
    assert len(result.declarations) == 1
    item = result.declarations[0]
    assert item.capability_id == "demo.search"
    assert item.kind == "provider_tool"
    assert item.tool_name == "demo_search"
    assert item.canonical_family == "web_search"
    assert item.declared_canonical_family == "web_search"
    assert item.canonical_family_source == "builtin"
    assert item.canonical_family_owner == "builtin"
    assert item.tool_capability_kind == "provider_native_tool"
    assert item.tool_runtime_binding == "provider_native"
    assert item.supported_profiles == ("codex_openai", "generic_chat")
    assert item.default_visibility == "model_visible"
    assert item.plugin_name == "demo_plugin"
    assert result.as_dicts()[0]["plugin_name"] == "demo_plugin"
    assert result.as_dicts()[0]["canonical_family_record"]["canonical_tool_names"] == ["web_search"]


def test_normalize_plugin_capability_declarations_accepts_media_capability_shape() -> None:
    result = capability_decl.normalize_plugin_capability_declarations(
        [
            {
                "capability_id": "demo.view_document",
                "kind": "provider_tool",
                "tool_name": "view_document",
                "canonical_family": "view_document",
                "supported_profiles": ["codex_openai", "generic_chat"],
                "default_visibility": "model_visible",
                "media_capability": {
                    "media_kind": "document",
                    "ingest_semantics": "shared_media_ingest_v1",
                    "source_modes": ["tool_path", "user_attachment", "tool_path"],
                    "projection_modes": ["tool_result_content_block", "message_native_attachment"],
                    "mime_types": ["application/pdf", "text/markdown", "application/pdf"],
                    "max_size_bytes": 5242880,
                },
            }
        ]
    )

    assert result.errors == ()
    assert len(result.declarations) == 1
    item = result.declarations[0]
    assert item.media_capability is not None
    assert item.canonical_family_source == "dynamic"
    assert item.tool_capability_kind == "local_runtime_tool"
    assert item.tool_runtime_binding == "shared_media_ingest"
    assert item.media_capability.media_kind == "document"
    assert item.media_capability.ingest_semantics == "shared_media_ingest_v1"
    assert item.media_capability.source_modes == ("tool_path", "user_attachment")
    assert item.media_capability.projection_modes == ("tool_result_content_block", "message_native_attachment")
    assert item.media_capability.mime_types == ("application/pdf", "text/markdown")
    assert item.media_capability.max_size_bytes == 5242880
    media_payload = result.as_dicts()[0]["media_capability"]
    assert media_payload["media_kind"] == "document"
    assert media_payload["source_modes"] == ["tool_path", "user_attachment"]
    assert media_payload["projection_modes"] == ["tool_result_content_block", "message_native_attachment"]
    assert media_payload["mime_types"] == ["application/pdf", "text/markdown"]
    assert media_payload["max_size_bytes"] == 5242880


def test_normalize_plugin_capability_declarations_degrades_invalid_rows_when_non_strict() -> None:
    result = capability_decl.normalize_plugin_capability_declarations(
        [
            {
                "capability_id": "ok.one",
                "kind": "provider_tool",
                "tool_name": "ok_tool",
                "canonical_family": "command_execution",
                "supported_profiles": ["generic_chat"],
                "default_visibility": "host_only",
            },
            {
                "capability_id": "bad.one",
                "kind": "provider_tool",
                "tool_name": "broken",
                "canonical_family": "command_execution",
                "supported_profiles": ["generic_chat"],
                "default_visibility": "model_visible",
                "media_capability": {
                    "media_kind": "unknown_media_kind",
                },
            },
        ],
        strict=False,
    )

    assert len(result.declarations) == 1
    assert result.declarations[0].capability_id == "ok.one"
    assert len(result.errors) == 1
    assert "invalid `media_kind`" in result.errors[0]


def test_normalize_plugin_capability_declarations_raises_in_strict_mode() -> None:
    with pytest.raises(ValueError):
        capability_decl.normalize_plugin_capability_declarations(
            [
                {
                    "capability_id": "bad.one",
                    "kind": "provider_tool",
                    "tool_name": "broken",
                    "canonical_family": "command_execution",
                    "supported_profiles": ["unknown_profile"],
                    "default_visibility": "model_visible",
                }
            ],
            strict=True,
        )


def test_normalize_plugin_capability_declarations_rejects_compatibility_alias_without_opt_in() -> None:
    result = capability_decl.normalize_plugin_capability_declarations(
        [
            {
                "capability_id": "demo.shell",
                "kind": "provider_tool",
                "tool_name": "demo_shell",
                "canonical_family": "shell",
                "supported_profiles": ["generic_chat"],
                "default_visibility": "model_visible",
            }
        ]
    )

    assert result.declarations == ()
    assert len(result.errors) == 1
    assert "compatibility alias" in result.errors[0]


def test_normalize_plugin_capability_declarations_accepts_compatibility_alias_with_opt_in() -> None:
    result = capability_decl.normalize_plugin_capability_declarations(
        [
            {
                "capability_id": "demo.shell",
                "kind": "provider_tool",
                "tool_name": "demo_shell",
                "canonical_family": "shell",
                "supported_profiles": ["generic_chat"],
                "default_visibility": "model_visible",
            }
        ],
        allow_compat_aliases=True,
    )

    assert result.errors == ()
    assert len(result.declarations) == 1
    item = result.declarations[0]
    assert item.canonical_family == "command_execution"
    assert item.canonical_family_alias_input == "shell"
    assert item.canonical_family_source == "builtin"
    assert item.tool_capability_kind == "local_runtime_tool"
    assert item.tool_runtime_binding == "local_runtime"


def test_normalize_plugin_capability_declarations_rejects_builtin_family_kind_mismatch() -> None:
    result = capability_decl.normalize_plugin_capability_declarations(
        [
            {
                "capability_id": "demo.search",
                "kind": "provider_tool",
                "tool_name": "demo_search",
                "canonical_family": "web_search",
                "tool_capability_kind": "local_runtime_tool",
                "supported_profiles": ["codex_openai"],
                "default_visibility": "model_visible",
            }
        ]
    )

    assert result.declarations == ()
    assert len(result.errors) == 1
    assert "requires tool_capability_kind `provider_native_tool`" in result.errors[0]


def test_load_plugin_capability_declarations_returns_empty_when_file_missing(tmp_path: Path) -> None:
    result = capability_decl.load_plugin_capability_declarations(tmp_path)
    assert result.declarations == ()
    assert result.errors == ()
    assert result.source_path == ""


def test_load_plugin_capability_declarations_reads_json_file(tmp_path: Path) -> None:
    payload = {
        "capabilities": [
            {
                "capability_id": "demo.patch",
                "kind": "provider_tool",
                "tool_name": "demo_patch",
                "canonical_family": "apply_patch",
                "supported_profiles": ["codex_openai"],
                "default_visibility": "model_visible",
            }
        ]
    }
    (tmp_path / "capabilities.json").write_text(json.dumps(payload), encoding="utf-8")

    result = capability_decl.load_plugin_capability_declarations(tmp_path)
    assert len(result.declarations) == 1
    assert result.errors == ()
    assert result.source_path.endswith("capabilities.json")
    assert result.declarations[0].capability_id == "demo.patch"


def test_load_plugin_capability_declarations_reads_toml_file(tmp_path: Path) -> None:
    (tmp_path / "capabilities.toml").write_text(
        """
[[capabilities]]
capability_id = "demo.shell"
kind = "provider_tool"
tool_name = "demo_shell"
canonical_family = "command_execution"
supported_profiles = ["generic_chat"]
default_visibility = "model_visible"
""".strip(),
        encoding="utf-8",
    )

    result = capability_decl.load_plugin_capability_declarations(tmp_path)
    assert len(result.declarations) == 1
    assert result.errors == ()
    assert result.source_path.endswith("capabilities.toml")
    assert result.declarations[0].capability_id == "demo.shell"


def test_plugin_manifest_and_loaded_plugin_expose_declaration_contract_defaults() -> None:
    manifest = PluginManifest(name="demo", version="0.1.0", description="demo")
    plugin = LoadedPlugin(
        manifest=manifest,
        plugin_name="demo",
        enabled=True,
        command_count=0,
        tool_count=0,
        connector_count=0,
        trigger_count=0,
        policy_count=0,
        workflow_count=0,
        provider_hooks={},
        runtime_hooks={},
        connector_registrations=[],
        trigger_registrations=[],
        policy_registrations=[],
        workflow_handlers=[],
    )

    assert manifest.capability_declarations == []
    assert plugin.capability_declarations == []
    assert plugin.capability_declaration_errors == []
