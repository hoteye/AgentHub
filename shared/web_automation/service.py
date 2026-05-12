from __future__ import annotations

from typing import Dict

from shared.web_automation.config import BrowserAutomationConfig, load_config
from shared.web_automation.live_driver import LiveBrowserDriver
from shared.web_automation.profiles import ensure_default_profile, resolve_profiles
from shared.web_automation.service_data_helpers import (
    _cookie_identity,
    _normalize_cookie,
    _normalize_storage_kind,
    _origin_for_url,
)
from shared.web_automation.service_interactions import BrowserServiceInteractionsMixin
from shared.web_automation.service_lifecycle import BrowserServiceLifecycleMixin
from shared.web_automation.service_observe_artifacts import BrowserServiceObserveArtifactsMixin
from shared.web_automation.service_profile_helpers import (
    HEX_COLOR_RE,
    _is_remote_profile,
    _normalize_profile_driver,
    _profile_has_cdp_channel,
    _serialize_profile_override,
    _supports_profile_reset,
)
from shared.web_automation.service_profiles_tabs import BrowserServiceProfilesTabsMixin
from shared.web_automation.service_state_io import (
    _deserialize_artifact,
    _deserialize_console,
    _deserialize_cookie,
    _deserialize_dialog_hook,
    _deserialize_ref,
    _deserialize_tab,
    _deserialize_upload_hook,
    _load_tabs,
    _persist_tabs,
    _serialize_dialog_hook,
    _serialize_tab,
    _serialize_upload_hook,
)
from shared.web_automation.storage import load_profile_overrides
from shared.web_automation.types import BrowserServiceState, ProfileState


class BrowserService(
    BrowserServiceLifecycleMixin,
    BrowserServiceProfilesTabsMixin,
    BrowserServiceObserveArtifactsMixin,
    BrowserServiceInteractionsMixin,
):
    def __init__(self) -> None:
        self.config: BrowserAutomationConfig = load_config()
        self._profile_overrides = load_profile_overrides()
        specs = resolve_profiles(self.config, overrides=self._profile_overrides)
        specs = ensure_default_profile(specs, self.config.default_profile)
        self.state = BrowserServiceState(enabled=bool(self.config.enabled), default_profile=self.config.default_profile)
        self._live_driver: LiveBrowserDriver | None = None
        self._debug_sessions: Dict[str, dict[str, object]] = {}
        for spec in specs.values():
            self.state.profiles[spec.name] = ProfileState(spec=spec)
        if self._is_live_mode():
            self._live_driver = LiveBrowserDriver(self.config)
        else:
            _load_tabs(self.state.profiles)

    def _is_live_mode(self) -> bool:
        return str(self.config.mode or "").strip().lower() == "live"

    def _persist_if_needed(self) -> None:
        if self._is_live_mode():
            return
        _persist_tabs(self.state.profiles)


__all__ = [
    "BrowserService",
    "HEX_COLOR_RE",
    "_load_tabs",
    "_persist_tabs",
    "_deserialize_tab",
    "_serialize_tab",
    "_deserialize_ref",
    "_deserialize_console",
    "_deserialize_artifact",
    "_deserialize_cookie",
    "_deserialize_upload_hook",
    "_serialize_upload_hook",
    "_deserialize_dialog_hook",
    "_serialize_dialog_hook",
    "_normalize_profile_driver",
    "_serialize_profile_override",
    "_is_remote_profile",
    "_supports_profile_reset",
    "_profile_has_cdp_channel",
    "_normalize_storage_kind",
    "_origin_for_url",
    "_normalize_cookie",
    "_cookie_identity",
]
