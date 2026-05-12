from __future__ import annotations

from pathlib import Path
import uuid
from typing import List, Optional

from shared.web_automation.observe import append_console_entry
from shared.web_automation.profiles import allocate_profile_color, get_used_colors, is_valid_profile_name
from shared.web_automation.service_profile_helpers import (
    HEX_COLOR_RE,
    _normalize_profile_driver,
    _serialize_profile_override,
    _supports_profile_reset,
)
from shared.web_automation.snapshot import ensure_tab_snapshot_seed
from shared.web_automation.storage import save_profile_overrides
from shared.web_automation.types import BrowserProfileSpec, BrowserTab, ProfileState


class BrowserServiceProfilesTabsMixin:
    def list_profiles(self) -> List[BrowserProfileSpec]:
        return [state.spec for state in self.state.profiles.values()]

    def create_profile(
        self,
        *,
        name: str,
        color: str | None = None,
        cdp_url: str | None = None,
        user_data_dir: str | None = None,
        driver: str | None = None,
        headless: bool | None = None,
        attach_only: bool | None = None,
    ) -> BrowserProfileSpec:
        profile_name = str(name or "").strip()
        if not profile_name:
            raise ValueError("name is required")
        if not is_valid_profile_name(profile_name):
            raise ValueError("invalid profile name: use lowercase letters, numbers, and hyphens only")
        if profile_name in self.state.profiles or profile_name in self.config.profiles:
            raise ValueError(f'profile "{profile_name}" already exists')

        normalized_driver = _normalize_profile_driver(driver)
        normalized_cdp_url = str(cdp_url or "").strip()
        normalized_user_data_dir = str(user_data_dir or "").strip()
        if normalized_user_data_dir and normalized_driver != "existing-session":
            raise ValueError("driver=existing-session is required when userDataDir is provided")
        if normalized_user_data_dir and not Path(normalized_user_data_dir).exists():
            raise ValueError(f"browser user data directory not found: {normalized_user_data_dir}")
        if normalized_cdp_url and normalized_driver == "existing-session":
            raise ValueError("driver=existing-session does not accept cdpUrl")

        used_colors = get_used_colors({name: state.spec for name, state in self.state.profiles.items()})
        requested_color = str(color or "").strip()
        profile_color = requested_color if HEX_COLOR_RE.fullmatch(requested_color) else allocate_profile_color(used_colors)
        spec = BrowserProfileSpec(
            name=profile_name,
            color=profile_color,
            driver=normalized_driver,
            default=False,
            attach_only=bool(attach_only) if attach_only is not None else normalized_driver == "existing-session",
            executable_path=self.config.executable_path,
            user_data_dir=normalized_user_data_dir,
            cdp_url=normalized_cdp_url,
            headless=headless if headless is not None else self.config.headless,
        )
        self._profile_overrides[profile_name] = _serialize_profile_override(spec)
        save_profile_overrides(self._profile_overrides)
        self.state.profiles[profile_name] = ProfileState(spec=spec)
        self._persist_if_needed()
        return spec

    def delete_profile(self, name: str) -> bool:
        profile_name = str(name or "").strip()
        if not profile_name:
            raise ValueError("profile name is required")
        if not is_valid_profile_name(profile_name):
            raise ValueError("invalid profile name")
        if profile_name == self.state.default_profile:
            raise ValueError(f'cannot delete the default profile "{profile_name}"')
        if profile_name in self.config.profiles and profile_name not in self._profile_overrides:
            raise ValueError(f'profile "{profile_name}" is config-managed and cannot be deleted dynamically')
        target = self.state.profiles.get(profile_name)
        if target is None:
            raise ValueError(f'profile "{profile_name}" not found')
        if target.running:
            self.stop(profile=profile_name)
        self.state.profiles.pop(profile_name, None)
        self._profile_overrides.pop(profile_name, None)
        save_profile_overrides(self._profile_overrides)
        self._persist_if_needed()
        return True

    def reset_profile(self, profile: Optional[str] = None) -> dict[str, object]:
        profile_name = profile or self.state.default_profile
        target = self.state.profiles.get(profile_name)
        if target is None:
            raise ValueError(f'profile "{profile_name}" not found')
        if not _supports_profile_reset(target.spec):
            raise ValueError(
                f'reset-profile is only supported for local profiles (profile "{profile_name}" is not resettable)'
            )
        cleared_tabs = len(target.tabs)
        stopped = False
        if target.running:
            stopped = bool(self.stop(profile=profile_name))
            target = self.state.profiles.get(profile_name)
            assert target is not None
        target.tabs = []
        target.active_tab = None
        self._persist_if_needed()
        return {"profile": profile_name, "stopped": stopped, "cleared_tabs": cleared_tabs}

    def list_tabs(self, profile: Optional[str] = None) -> List[BrowserTab]:
        target = self.state.profiles.get(profile or self.state.default_profile)
        return list(target.tabs) if target else []

    def open_tab(self, url: str, profile: Optional[str] = None) -> Optional[BrowserTab]:
        target = self.state.profiles.get(profile or self.state.default_profile)
        if not target or not target.running:
            return None
        if self._is_live_mode():
            assert self._live_driver is not None
            tab = self._live_driver.open_tab(target, url)
            target.tabs.append(tab)
            target.active_tab = tab.tab_id
            return tab
        tab = BrowserTab(tab_id=uuid.uuid4().hex, url=url, title=url, profile=target.spec.name)
        ensure_tab_snapshot_seed(tab)
        append_console_entry(
            tab,
            message_type="info",
            text=f"Opened synthetic tab for {tab.url}",
            location={"url": tab.url},
        )
        target.tabs.append(tab)
        target.active_tab = tab.tab_id
        self._persist_if_needed()
        return tab

    def focus_tab(self, tab_id: str, profile: Optional[str] = None) -> bool:
        target = self.state.profiles.get(profile or self.state.default_profile)
        if not target:
            return False
        for tab in target.tabs:
            if tab.tab_id == tab_id:
                if self._is_live_mode():
                    assert self._live_driver is not None
                    if not self._live_driver.focus_tab(tab):
                        return False
                target.active_tab = tab_id
                return True
        return False

    def close_tab(self, tab_id: str, profile: Optional[str] = None) -> bool:
        target = self.state.profiles.get(profile or self.state.default_profile)
        if not target:
            return False
        live_tab = None
        if self._is_live_mode():
            for tab in target.tabs:
                if tab.tab_id == tab_id:
                    live_tab = tab
                    break
        tabs = [tab for tab in target.tabs if tab.tab_id != tab_id]
        if len(tabs) == len(target.tabs):
            return False
        if self._is_live_mode() and live_tab is not None:
            assert self._live_driver is not None
            self._live_driver.close_tab(live_tab)
        target.tabs = tabs
        target.active_tab = tabs[-1].tab_id if tabs else None
        self._persist_if_needed()
        return True

    def navigate(self, url: str, profile: Optional[str] = None) -> Optional[BrowserTab]:
        target = self.state.profiles.get(profile or self.state.default_profile)
        if not target or not target.running:
            return None
        if target.active_tab:
            for tab in target.tabs:
                if tab.tab_id == target.active_tab:
                    if self._is_live_mode():
                        assert self._live_driver is not None
                        return self._live_driver.navigate(tab, url)
                    tab.url = url
                    tab.title = url
                    tab.text = ""
                    tab.refs = []
                    ensure_tab_snapshot_seed(tab)
                    append_console_entry(
                        tab,
                        message_type="info",
                        text=f"Navigated synthetic tab to {tab.url}",
                        location={"url": tab.url},
                    )
                    self._persist_if_needed()
                    return tab
        return self.open_tab(url, profile=profile)

