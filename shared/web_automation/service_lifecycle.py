from __future__ import annotations

from typing import Optional

from shared.web_automation.service_profile_helpers import _profile_has_cdp_channel
from shared.web_automation.types import BrowserStatus


class BrowserServiceLifecycleMixin:
    def status(self) -> BrowserStatus:
        active_profile = self.state.default_profile
        default_state = self.state.profiles.get(active_profile)
        return BrowserStatus(
            running=bool(default_state and default_state.running),
            active_profile=active_profile,
            active_tab=(default_state.active_tab if default_state else None),
            profile_count=len(self.state.profiles),
        )

    def connection_hints(self, profile: Optional[str] = None) -> dict[str, object]:
        profile_name = str(profile or self.state.default_profile or "").strip() or self.state.default_profile
        profile_state = self.state.profiles.get(profile_name)
        spec = profile_state.spec if profile_state is not None else None
        cdp_http = _profile_has_cdp_channel(spec)
        cdp_ready = False
        if cdp_http and self._is_live_mode() and self._live_driver is not None:
            cdp_ready = profile_name in self._live_driver._contexts
        return {
            "cdp_http": cdp_http,
            "cdp_ready": cdp_ready,
        }

    def start(self, profile: Optional[str] = None) -> bool:
        profile_name = profile or self.state.default_profile
        target = self.state.profiles.get(profile_name)
        if not target:
            return False
        if self._is_live_mode():
            assert self._live_driver is not None
            self._live_driver.start_profile(target)
        target.running = True
        self._persist_if_needed()
        return True

    def shutdown(self) -> None:
        if not self._is_live_mode() or self._live_driver is None:
            return
        for profile_state in self.state.profiles.values():
            try:
                self._live_driver.stop_profile(profile_state)
            except Exception:
                continue
            profile_state.running = False
            profile_state.tabs = []
            profile_state.active_tab = None

    def stop(self, profile: Optional[str] = None) -> bool:
        profile_name = profile or self.state.default_profile
        target = self.state.profiles.get(profile_name)
        if not target:
            return False
        if self._is_live_mode():
            assert self._live_driver is not None
            self._live_driver.stop_profile(target)
        target.tabs = []
        target.active_tab = None
        target.running = False
        self._persist_if_needed()
        return True

