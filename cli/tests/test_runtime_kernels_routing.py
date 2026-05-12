from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli.runtime_kernels.routing import (
    codex_sidecar_default_for_openai_enabled,
    normalize_kernel_engine,
    openai_codex_provider_status,
    select_new_tab_engine,
    sidecar_provider_hint_lines,
)


class RuntimeKernelRoutingTest(unittest.TestCase):
    def test_normalize_kernel_engine_accepts_openai_aliases(self) -> None:
        self.assertEqual(normalize_kernel_engine("python"), "agenthub_python")
        self.assertEqual(normalize_kernel_engine("openai"), "codex_sidecar")
        self.assertEqual(normalize_kernel_engine("openai-codex"), "codex_sidecar")
        self.assertIsNone(normalize_kernel_engine("unknown"))

    def test_default_for_openai_reads_env_before_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                "[runtime_kernels.codex_sidecar]\ndefault_for_openai = true\n",
                encoding="utf-8",
            )

            self.assertTrue(
                codex_sidecar_default_for_openai_enabled(env={}, config_paths=[config_path])
            )
            self.assertFalse(
                codex_sidecar_default_for_openai_enabled(
                    env={"AGENTHUB_CODEX_SIDECAR_DEFAULT_FOR_OPENAI": "0"},
                    config_paths=[config_path],
                )
            )

    def test_openai_codex_provider_status_detects_responses_wire(self) -> None:
        self.assertTrue(
            openai_codex_provider_status(
                {
                    "provider_name": "openai",
                    "wire_api": "responses",
                }
            )
        )
        self.assertFalse(
            openai_codex_provider_status(
                {
                    "provider_name": "anthropic",
                    "wire_api": "responses",
                }
            )
        )

    def test_select_new_tab_engine_requires_toggle_provider_and_artifact(self) -> None:
        runtime = _runtime_with_status({"provider_name": "openai", "wire_api": "responses"})

        self.assertEqual(
            select_new_tab_engine(
                runtime,
                env={"AGENTHUB_CODEX_SIDECAR_DEFAULT_FOR_OPENAI": "1"},
                config_paths=[],
                artifact_available_fn=lambda: True,
            ),
            "codex_sidecar",
        )
        self.assertEqual(
            select_new_tab_engine(
                runtime,
                env={"AGENTHUB_CODEX_SIDECAR_DEFAULT_FOR_OPENAI": "1"},
                config_paths=[],
                artifact_available_fn=lambda: False,
            ),
            "agenthub_python",
        )
        self.assertEqual(
            select_new_tab_engine(
                _runtime_with_status({"provider_name": "anthropic", "wire_api": "responses"}),
                env={"AGENTHUB_CODEX_SIDECAR_DEFAULT_FOR_OPENAI": "1"},
                config_paths=[],
                artifact_available_fn=lambda: True,
            ),
            "agenthub_python",
        )

    def test_select_new_tab_engine_uses_provider_config_when_status_is_stale(self) -> None:
        runtime = SimpleNamespace(
            agent=SimpleNamespace(
                provider_status=lambda: {
                    "provider_name": "anthropic",
                    "wire_api": "anthropic_messages",
                },
                _provider_config=SimpleNamespace(
                    provider_name="openai",
                    planner_kind="openai_responses",
                    wire_api="responses",
                    interaction_profile="codex_openai",
                    model="gpt-5.4",
                ),
            )
        )

        self.assertEqual(
            select_new_tab_engine(
                runtime,
                env={"AGENTHUB_CODEX_SIDECAR_DEFAULT_FOR_OPENAI": "1"},
                config_paths=[],
                artifact_available_fn=lambda: True,
            ),
            "codex_sidecar",
        )

    def test_select_new_tab_engine_env_override_wins(self) -> None:
        runtime = _runtime_with_status({"provider_name": "anthropic"})

        self.assertEqual(
            select_new_tab_engine(
                runtime,
                env={"AGENTHUB_RUNTIME_ENGINE": "codex"},
                config_paths=[],
                artifact_available_fn=lambda: False,
            ),
            "codex_sidecar",
        )

    def test_sidecar_provider_hint_lines(self) -> None:
        self.assertEqual(
            sidecar_provider_hint_lines(
                {
                    "provider_source": "codex_sidecar",
                    "codex_sidecar_source": "bundled",
                }
            ),
            ["runtime_kernel=codex_sidecar", "codex_sidecar_source=bundled"],
        )
        self.assertTrue(
            sidecar_provider_hint_lines(
                {
                    "provider_name": "openai",
                    "wire_api": "responses",
                }
            )
        )


def _runtime_with_status(status: dict[str, object]) -> object:
    return SimpleNamespace(
        agent=SimpleNamespace(provider_status=lambda: status),
    )


if __name__ == "__main__":
    unittest.main()
