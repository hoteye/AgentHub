from __future__ import annotations

from pathlib import Path

from shared.web_automation.actions import perform_tab_action
from shared.web_automation.artifacts import create_artifact_path, resolve_artifact_output_path
from shared.web_automation.hooks import arm_dialog_hook, arm_upload_hook
from shared.web_automation.service_data_helpers import (
    _cookie_identity,
    _normalize_cookie,
    _normalize_storage_kind,
    _origin_for_url,
)
from shared.web_automation.types import BrowserPageRef, BrowserTab


class BrowserServiceInteractionsMixin:
    def cookies(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
    ) -> list[dict[str, object]] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        if not self._is_live_mode():
            return [dict(item) for item in tab.cookies]
        assert self._live_driver is not None
        return self._live_driver.get_cookies(tab)

    def get_cookies(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
    ) -> list[dict[str, object]]:
        cookies = self.cookies(target_id=target_id, profile=profile)
        return [dict(item) for item in list(cookies or [])]

    def set_cookies(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        cookies: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            raise ValueError("target tab not found")
        normalized_cookies = [_normalize_cookie(item, tab=tab) for item in list(cookies or []) if isinstance(item, dict)]
        if not normalized_cookies:
            raise ValueError("cookies must contain at least one cookie")
        if self._is_live_mode():
            assert self._live_driver is not None
            self._live_driver.set_cookies(tab, normalized_cookies)
            current = self._live_driver.get_cookies(tab)
        else:
            merged = {
                _cookie_identity(item): dict(item)
                for item in tab.cookies
            }
            for item in normalized_cookies:
                merged[_cookie_identity(item)] = dict(item)
            tab.cookies = list(merged.values())
            self._persist_if_needed()
            current = [dict(item) for item in tab.cookies]
        return {
            "ok": True,
            "target_id": tab.tab_id,
            "count": len(normalized_cookies),
            "cookies": current,
        }

    def clear_cookies(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
    ) -> dict[str, object]:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            raise ValueError("target tab not found")
        if self._is_live_mode():
            assert self._live_driver is not None
            cleared = self._live_driver.clear_cookies(tab)
        else:
            cleared = len(tab.cookies)
            tab.cookies = []
            self._persist_if_needed()
        return {"ok": True, "target_id": tab.tab_id, "cleared": int(cleared)}

    def storage_state(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
    ) -> dict[str, object] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        if not self._is_live_mode():
            origin = _origin_for_url(tab.url)
            if not origin or (not tab.local_storage and not tab.session_storage):
                return {"origins": []}
            return {
                "origins": [
                    {
                        "origin": origin,
                        "localStorage": [
                            {"name": key, "value": value}
                            for key, value in sorted(tab.local_storage.items())
                        ],
                        "sessionStorage": [
                            {"name": key, "value": value}
                            for key, value in sorted(tab.session_storage.items())
                        ],
                    }
                ]
            }
        assert self._live_driver is not None
        return self._live_driver.get_storage_state(tab)

    def get_storage(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        storage_kind: str,
    ) -> dict[str, str]:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            raise ValueError("target tab not found")
        normalized_kind = _normalize_storage_kind(storage_kind)
        if self._is_live_mode():
            assert self._live_driver is not None
            return self._live_driver.get_storage(tab, storage_kind=normalized_kind)
        source = tab.local_storage if normalized_kind == "local" else tab.session_storage
        return dict(source)

    def set_storage(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        storage_kind: str,
        items: dict[str, object] | None = None,
    ) -> dict[str, object]:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            raise ValueError("target tab not found")
        normalized_kind = _normalize_storage_kind(storage_kind)
        normalized_items = {
            str(key).strip(): str(value)
            for key, value in (items or {}).items()
            if str(key).strip()
        }
        if not normalized_items:
            raise ValueError("items must contain at least one storage entry")
        if self._is_live_mode():
            assert self._live_driver is not None
            self._live_driver.set_storage(tab, storage_kind=normalized_kind, items=normalized_items)
            current = self._live_driver.get_storage(tab, storage_kind=normalized_kind)
        else:
            target_store = tab.local_storage if normalized_kind == "local" else tab.session_storage
            target_store.update(normalized_items)
            self._persist_if_needed()
            current = dict(target_store)
        return {
            "ok": True,
            "target_id": tab.tab_id,
            "storage_kind": normalized_kind,
            "count": len(normalized_items),
            "items": current,
        }

    def clear_storage(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        storage_kind: str,
    ) -> dict[str, object]:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            raise ValueError("target tab not found")
        normalized_kind = _normalize_storage_kind(storage_kind)
        if self._is_live_mode():
            assert self._live_driver is not None
            cleared = self._live_driver.clear_storage(tab, storage_kind=normalized_kind)
        else:
            target_store = tab.local_storage if normalized_kind == "local" else tab.session_storage
            cleared = len(target_store)
            target_store.clear()
            self._persist_if_needed()
        return {
            "ok": True,
            "target_id": tab.tab_id,
            "storage_kind": normalized_kind,
            "cleared": int(cleared),
        }

    def act(
        self,
        *,
        kind: str,
        target_id: str | None = None,
        profile: str | None = None,
        ref: str | None = None,
        start_ref: str | None = None,
        end_ref: str | None = None,
        text: str | None = None,
        key: str | None = None,
        values: list[str] | None = None,
        fields: list[dict[str, object]] | None = None,
        time_ms: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, object] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        normalized_kind = str(kind or "").strip().lower()
        if self._is_live_mode():
            assert self._live_driver is not None
            if normalized_kind == "click":
                result = self._live_driver.click(tab, ref=str(ref or "").strip())
            elif normalized_kind == "double_click":
                result = self._live_driver.double_click(tab, ref=str(ref or "").strip())
            elif normalized_kind == "hover":
                result = self._live_driver.hover(tab, ref=str(ref or "").strip())
            elif normalized_kind == "scroll_into_view":
                result = self._live_driver.scroll_into_view(tab, ref=str(ref or "").strip())
            elif normalized_kind == "focus":
                result = self._live_driver.focus_ref(tab, ref=str(ref or "").strip())
            elif normalized_kind == "type":
                result = self._live_driver.type_text(tab, ref=str(ref or "").strip(), text=str(text or ""))
            elif normalized_kind == "clear":
                result = self._live_driver.clear_field(tab, ref=str(ref or "").strip())
            elif normalized_kind == "press":
                result = self._live_driver.press_key(tab, key=str(key or "").strip())
            elif normalized_kind == "check":
                result = self._live_driver.check(tab, ref=str(ref or "").strip())
            elif normalized_kind == "uncheck":
                result = self._live_driver.uncheck(tab, ref=str(ref or "").strip())
            elif normalized_kind == "drag":
                result = self._live_driver.drag(
                    tab,
                    start_ref=str(start_ref or ref or "").strip(),
                    end_ref=str(end_ref or "").strip(),
                )
            elif normalized_kind == "resize":
                result = self._live_driver.resize_viewport(
                    tab,
                    width=int(width or 0),
                    height=int(height or 0),
                )
            elif normalized_kind == "select":
                result = self._live_driver.select_values(tab, ref=str(ref or "").strip(), values=list(values or []))
            elif normalized_kind == "fill":
                result = self._live_driver.fill_fields(tab, fields=list(fields or []))
            elif normalized_kind == "wait":
                result = self._live_driver.wait_time(tab, time_ms=int(time_ms or 0))
            elif normalized_kind == "evaluate":
                if not self.config.evaluate_enabled:
                    raise ValueError("browser evaluate is disabled by config (browser.evaluate_enabled=false)")
                result = self._live_driver.evaluate_script(
                    tab,
                    fn=str(text or ""),
                    ref=(str(ref).strip() if ref is not None else None),
                )
            else:
                raise ValueError(f"unsupported browser act kind: {kind}")
            self._persist_if_needed()
            return result
        result = perform_tab_action(
            tab,
            kind=kind,
            ref=ref,
            start_ref=start_ref,
            end_ref=end_ref,
            text=text,
            key=key,
            values=values,
            fields=fields,
            time_ms=time_ms,
            width=width,
            height=height,
            evaluate_enabled=self.config.evaluate_enabled,
        )
        self._persist_if_needed()
        return result

    def upload(
        self,
        *,
        paths: list[str],
        target_id: str | None = None,
        profile: str | None = None,
        ref: str | None = None,
        input_ref: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, object] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        result = arm_upload_hook(
            tab,
            paths=paths,
            ref=ref,
            input_ref=input_ref,
            timeout_ms=timeout_ms,
        )
        self._persist_if_needed()
        return result

    def dialog(
        self,
        *,
        accept: bool = True,
        prompt_text: str | None = None,
        target_id: str | None = None,
        profile: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, object] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        result = arm_dialog_hook(
            tab,
            accept=accept,
            prompt_text=prompt_text,
            timeout_ms=timeout_ms,
        )
        self._persist_if_needed()
        return result

    def _resolve_tab(self, *, target_id: str | None = None, profile: str | None = None) -> BrowserTab | None:
        if target_id:
            if profile:
                target_profile = self.state.profiles.get(profile)
                if not target_profile:
                    return None
                for tab in target_profile.tabs:
                    if tab.tab_id == target_id:
                        return tab
                return None
            for candidate_profile in self.state.profiles.values():
                for tab in candidate_profile.tabs:
                    if tab.tab_id == target_id:
                        return tab
            return None

        target_profile = self.state.profiles.get(profile or self.state.default_profile)
        if not target_profile or not target_profile.tabs:
            return None
        if target_profile.active_tab:
            for tab in target_profile.tabs:
                if tab.tab_id == target_profile.active_tab:
                    return tab
        return target_profile.tabs[-1]

    @staticmethod
    def _require_ref(tab: BrowserTab, ref: str) -> BrowserPageRef:
        normalized = str(ref or "").strip()
        if not normalized:
            raise ValueError("action requires ref")
        for item in tab.refs:
            if item.ref == normalized:
                return item
        raise ValueError(f"unknown ref: {normalized}")

    @staticmethod
    def _trace_output_path(tab: BrowserTab, *, trace_id: str, requested_path: str | None) -> Path:
        if str(requested_path or "").strip():
            return resolve_artifact_output_path("traces", str(requested_path))
        return create_artifact_path("traces", f"{tab.tab_id}-{trace_id}.zip")

