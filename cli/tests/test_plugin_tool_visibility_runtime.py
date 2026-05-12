from __future__ import annotations

from cli.agent_cli.providers import plugin_tool_visibility_runtime as runtime


def _task_a_declaration(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "tool_name": "demo_lookup",
        "canonical_family": "demo_lookup",
        "canonical_family_source": "dynamic",
        "canonical_family_owner": "demo_plugin",
        "tool_capability_kind": "local_runtime_tool",
        "tool_runtime_binding": "plugin_runtime",
        "supported_profiles": ["generic_chat"],
        "default_visibility": "model_visible",
        "canonical_family_record": {
            "canonical_family": "demo_lookup",
            "family_source": "dynamic",
            "family_owner": "demo_plugin",
            "canonical_tool_names": ["demo_lookup"],
            "compatibility_aliases": [],
            "tool_capability_kind": "local_runtime_tool",
            "tool_runtime_binding": "plugin_runtime",
        },
    }
    payload.update(overrides)
    return payload


def test_plugin_tool_declarations_by_name_prefers_manager_declarations() -> None:
    class _Manager:
        def provider_tool_capability_declarations(self):  # noqa: ANN201
            return [
                _task_a_declaration()
            ]

    specs = [
        {
            "type": "function",
            "function": {"name": "demo_lookup"},
            "x_agenthub_plugin_capability": {
                "canonical_family": "demo_lookup",
                "tool_capability_kind": "local_runtime_tool",
                "tool_runtime_binding": "plugin_runtime",
                "supported_profiles": ["codex_openai"],
                "default_visibility": "disabled",
            },
        }
    ]
    by_name = runtime.plugin_tool_declarations_by_name(
        manager=_Manager(),
        plugin_specs=specs,
        function_name_from_spec=lambda item: str(item.get("function", {}).get("name") or ""),
    )

    assert by_name["demo_lookup"]["supported_profiles"] == ["generic_chat"]
    assert by_name["demo_lookup"]["default_visibility"] == "model_visible"


def test_plugin_tool_projection_decision_exposes_task_a_aligned_local_runtime_tool() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="demo_lookup",
        tool_surface_profile="generic_chat",
        declarations_by_name={
            "demo_lookup": _task_a_declaration(),
        },
    )

    assert decision.outcome == "expose_tool"
    assert decision.reason == "local_runtime_tool_supported"
    assert runtime.plugin_tool_visible_for_profile(
        function_name="demo_lookup",
        tool_surface_profile="generic_chat",
        declarations_by_name={"demo_lookup": _task_a_declaration()},
    ) is True


def test_plugin_tool_visible_for_profile_hides_undeclared_tool() -> None:
    assert (
        runtime.plugin_tool_visible_for_profile(
            function_name="demo_lookup",
            tool_surface_profile="generic_chat",
            declarations_by_name={},
        )
        is False
    )


def test_plugin_tool_projection_decision_requires_task_a_canonical_alignment() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="demo_lookup",
        tool_surface_profile="generic_chat",
        declarations_by_name={
            "demo_lookup": {
                "supported_profiles": ["generic_chat"],
                "default_visibility": "model_visible",
            }
        },
    )

    assert decision.outcome == "hide"
    assert decision.reason == "canonical_alignment_required"


def test_plugin_tool_projection_decision_hides_non_model_visible_tool() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="demo_lookup",
        tool_surface_profile="generic_chat",
        declarations_by_name={
            "demo_lookup": _task_a_declaration(default_visibility="host_only"),
        },
    )

    assert decision.outcome == "hide"
    assert decision.reason == "default_visibility_not_model_visible"


def test_plugin_tool_projection_decision_hides_profile_mismatch() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="demo_lookup",
        tool_surface_profile="codex_openai",
        declarations_by_name={
            "demo_lookup": _task_a_declaration(supported_profiles=["generic_chat"]),
        },
    )

    assert decision.outcome == "hide"
    assert decision.reason == "profile_not_supported"


def test_plugin_tool_projection_decision_allows_generic_chat_declaration_for_claude_code() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="demo_lookup",
        tool_surface_profile="claude_code",
        declarations_by_name={
            "demo_lookup": _task_a_declaration(supported_profiles=["generic_chat"]),
        },
    )

    assert decision.outcome == "expose_tool"
    assert decision.reason == "local_runtime_tool_supported"


def test_plugin_tool_projection_decision_accepts_supported_media_capability() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="view_document",
        tool_surface_profile="generic_chat",
        declarations_by_name={
            "view_document": _task_a_declaration(
                tool_name="view_document",
                canonical_family="view_document",
                canonical_family_record={
                    "canonical_family": "view_document",
                    "family_source": "dynamic",
                    "family_owner": "demo_plugin",
                    "canonical_tool_names": ["view_document"],
                    "compatibility_aliases": [],
                    "tool_capability_kind": "local_runtime_tool",
                    "tool_runtime_binding": "shared_media_ingest",
                },
                tool_runtime_binding="shared_media_ingest",
                media_capability={
                    "media_kind": "document",
                    "ingest_semantics": "shared_media_ingest_v1",
                    "source_modes": ["tool_path", "user_attachment"],
                    "projection_modes": ["tool_result_content_block"],
                    "mime_types": ["application/pdf", "text/markdown"],
                    "max_size_bytes": 4096,
                },
            )
        },
    )

    assert decision.outcome == "expose_tool"
    assert decision.reason == "shared_media_ingest_supported"


def test_view_document_projection_decision_accepts_extraction_only_profile_matrix() -> None:
    for tool_surface_profile in ("codex_openai", "claude_code", "generic_chat"):
        decision = runtime.plugin_tool_projection_decision(
            function_name="view_document",
            tool_surface_profile=tool_surface_profile,
            declarations_by_name={
                "view_document": _task_a_declaration(
                    tool_name="view_document",
                    canonical_family="view_document",
                    supported_profiles=[tool_surface_profile],
                    canonical_family_record={
                        "canonical_family": "view_document",
                        "family_source": "dynamic",
                        "family_owner": "demo_plugin",
                        "canonical_tool_names": ["view_document"],
                        "compatibility_aliases": [],
                        "tool_capability_kind": "local_runtime_tool",
                        "tool_runtime_binding": "shared_media_ingest",
                    },
                    tool_runtime_binding="shared_media_ingest",
                    media_capability={
                        "media_kind": "document",
                        "ingest_semantics": "shared_media_ingest_v1",
                        "source_modes": ["tool_path"],
                        "projection_modes": ["tool_result_content_block"],
                        "mime_types": ["text/markdown", "application/json"],
                    },
                )
            },
        )

        assert decision.outcome == "expose_tool"
        assert decision.reason == "shared_media_ingest_supported"


def test_view_document_projection_decision_rejects_message_native_only_generic_chat_capability() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="view_document",
        tool_surface_profile="generic_chat",
        declarations_by_name={
            "view_document": _task_a_declaration(
                tool_name="view_document",
                canonical_family="view_document",
                supported_profiles=["generic_chat"],
                canonical_family_record={
                    "canonical_family": "view_document",
                    "family_source": "dynamic",
                    "family_owner": "demo_plugin",
                    "canonical_tool_names": ["view_document"],
                    "compatibility_aliases": [],
                    "tool_capability_kind": "local_runtime_tool",
                    "tool_runtime_binding": "shared_media_ingest",
                },
                tool_runtime_binding="shared_media_ingest",
                media_capability={
                    "media_kind": "document",
                    "ingest_semantics": "shared_media_ingest_v1",
                    "source_modes": ["tool_path"],
                    "projection_modes": ["message_native_attachment"],
                    "mime_types": ["application/pdf"],
                },
            )
        },
    )

    assert decision.outcome == "hide"
    assert decision.reason == "shared_media_ingest_projection_unsupported"


def test_plugin_tool_visible_for_profile_hides_media_capability_with_unsupported_projection() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="view_image",
        tool_surface_profile="generic_chat",
        declarations_by_name={
            "view_image": _task_a_declaration(
                tool_name="view_image",
                canonical_family="view_image",
                canonical_family_record={
                    "canonical_family": "view_image",
                    "family_source": "dynamic",
                    "family_owner": "demo_plugin",
                    "canonical_tool_names": ["view_image"],
                    "compatibility_aliases": [],
                    "tool_capability_kind": "local_runtime_tool",
                    "tool_runtime_binding": "shared_media_ingest",
                },
                tool_runtime_binding="shared_media_ingest",
                media_capability={
                    "media_kind": "image",
                    "ingest_semantics": "shared_media_ingest_v1",
                    "source_modes": ["user_attachment"],
                    "projection_modes": ["message_native_attachment"],
                    "mime_types": ["image/png"],
                },
            )
        },
    )

    assert decision.outcome == "hide"
    assert decision.reason == "shared_media_ingest_projection_unsupported"


def test_plugin_tool_visible_for_profile_hides_invalid_media_capability_shape() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="view_document",
        tool_surface_profile="codex_openai",
        declarations_by_name={
            "view_document": _task_a_declaration(
                tool_name="view_document",
                supported_profiles=["codex_openai"],
                canonical_family="view_document",
                canonical_family_record={
                    "canonical_family": "view_document",
                    "family_source": "dynamic",
                    "family_owner": "demo_plugin",
                    "canonical_tool_names": ["view_document"],
                    "compatibility_aliases": [],
                    "tool_capability_kind": "local_runtime_tool",
                    "tool_runtime_binding": "shared_media_ingest",
                },
                tool_runtime_binding="shared_media_ingest",
                media_capability={
                    "media_kind": "document",
                    "ingest_semantics": "shared_media_ingest_v1",
                    "source_modes": ["tool_path"],
                    "projection_modes": ["tool_result_content_block"],
                    "mime_types": ["not-a-mime"],
                    "max_size_bytes": 0,
                },
            )
        },
    )

    assert decision.outcome == "hide"
    assert decision.reason == "shared_media_ingest_projection_unsupported"


def test_plugin_tool_projection_decision_marks_provider_native_tool_as_native_only() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="demo_search",
        tool_surface_profile="codex_openai",
        declarations_by_name={
            "demo_search": _task_a_declaration(
                tool_name="demo_search",
                canonical_family="web_search",
                canonical_family_source="builtin",
                canonical_family_owner="builtin",
                tool_capability_kind="provider_native_tool",
                tool_runtime_binding="provider_native",
                supported_profiles=["codex_openai"],
                canonical_family_record={
                    "canonical_family": "web_search",
                    "family_source": "builtin",
                    "family_owner": "builtin",
                    "canonical_tool_names": ["web_search"],
                    "compatibility_aliases": [],
                    "tool_capability_kind": "provider_native_tool",
                    "tool_runtime_binding": "provider_native",
                },
            )
        },
    )

    assert decision.outcome == "native_only"
    assert decision.reason == "provider_native_requires_adapter_projection"
    assert decision.include_in_tool_registry is False


def test_plugin_tool_projection_decision_exposes_provider_native_fallback_tool_for_claude_code() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="demo_search",
        tool_surface_profile="claude_code",
        declarations_by_name={
            "demo_search": _task_a_declaration(
                tool_name="demo_search",
                canonical_family="web_search",
                canonical_family_source="builtin",
                canonical_family_owner="builtin",
                tool_capability_kind="provider_native_tool",
                tool_runtime_binding="provider_native",
                supported_profiles=["generic_chat"],
                canonical_family_record={
                    "canonical_family": "web_search",
                    "family_source": "builtin",
                    "family_owner": "builtin",
                    "canonical_tool_names": ["web_search"],
                    "compatibility_aliases": [],
                    "tool_capability_kind": "provider_native_tool",
                    "tool_runtime_binding": "provider_native",
                },
            )
        },
    )

    assert decision.outcome == "expose_tool"
    assert decision.reason == "provider_native_fallback_function_tool_supported"
    assert decision.include_in_tool_registry is True


def test_plugin_tool_projection_decision_never_exposes_ui_only_capability() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="tool_search",
        tool_surface_profile="generic_chat",
        declarations_by_name={
            "tool_search": _task_a_declaration(
                tool_name="tool_search",
                canonical_family="tool_search",
                tool_capability_kind="ui_only_capability",
                tool_runtime_binding="plugin_runtime",
                canonical_family_record={
                    "canonical_family": "tool_search",
                    "family_source": "dynamic",
                    "family_owner": "demo_plugin",
                    "canonical_tool_names": ["tool_search"],
                    "compatibility_aliases": [],
                    "tool_capability_kind": "ui_only_capability",
                    "tool_runtime_binding": "plugin_runtime",
                },
            )
        },
    )

    assert decision.outcome == "hide"
    assert decision.reason == "ui_only_capability_never_model_visible"


def test_plugin_tool_projection_decision_marks_message_native_capability_as_message_only() -> None:
    decision = runtime.plugin_tool_projection_decision(
        function_name="user_image_input",
        tool_surface_profile="claude_code",
        declarations_by_name={
            "user_image_input": _task_a_declaration(
                tool_name="user_image_input",
                canonical_family="user_image_input",
                tool_capability_kind="message_native_capability",
                tool_runtime_binding="shared_media_ingest",
                supported_profiles=["claude_code"],
                canonical_family_record={
                    "canonical_family": "user_image_input",
                    "family_source": "dynamic",
                    "family_owner": "demo_plugin",
                    "canonical_tool_names": ["user_image_input"],
                    "compatibility_aliases": [],
                    "tool_capability_kind": "message_native_capability",
                    "tool_runtime_binding": "shared_media_ingest",
                },
                media_capability={
                    "media_kind": "image",
                    "ingest_semantics": "shared_media_ingest_v1",
                    "source_modes": ["user_attachment"],
                    "projection_modes": ["message_native_attachment"],
                    "mime_types": ["image/png"],
                },
            )
        },
    )

    assert decision.outcome == "message_only"
    assert decision.reason == "message_native_capability_only"
    assert decision.include_in_tool_registry is False
