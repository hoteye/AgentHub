from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

CODEX_HOME_ENV = "CODEX_HOME"
CODEX_API_KEY_ENV = "CODEX_API_KEY"
CODEX_AUTH_JSON_API_KEY = "OPENAI_API_KEY"
DEFAULT_PROJECTED_CODEX_HOME_DIR = "codex_sidecar/codex_home"
DEFAULT_SCRUBBED_AUTH_ENV_KEYS = (CODEX_API_KEY_ENV, CODEX_AUTH_JSON_API_KEY)


@dataclass(frozen=True, slots=True)
class CodexSidecarProjectedConfig:
    codex_home: Path
    config_path: Path
    auth_path: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    provider_name: str = ""
    model: str = ""
    codex_provider_id: str = ""
    source_config_path: str = ""
    source_auth_path: str = ""
    auth_key_names: tuple[str, ...] = ()
    scrubbed_env_keys: tuple[str, ...] = ()
    generated: bool = False

    def status_fields(self) -> dict[str, str]:
        status = {
            "codex_sidecar_config_source": "agenthub_projected" if self.generated else "external",
            "codex_sidecar_codex_home": str(self.codex_home),
            "codex_sidecar_config_path": str(self.config_path),
        }
        if self.provider_name:
            status["codex_sidecar_agenthub_provider"] = self.provider_name
        if self.codex_provider_id:
            status["codex_sidecar_model_provider"] = self.codex_provider_id
        if self.model:
            status["codex_sidecar_config_model"] = self.model
        if self.source_config_path:
            status["codex_sidecar_source_config_path"] = self.source_config_path
        if self.source_auth_path:
            status["codex_sidecar_source_auth_path"] = self.source_auth_path
        if self.auth_path is not None:
            status["codex_sidecar_auth_path"] = str(self.auth_path)
        if self.auth_key_names:
            status["codex_sidecar_auth_key_names"] = ",".join(self.auth_key_names)
            status["codex_sidecar_auth_source"] = "agenthub_auth_store"
            status["codex_sidecar_auth_transport"] = "codex_auth_json"
        return status
