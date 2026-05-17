from __future__ import annotations

from shared.web_automation.artifacts import (
    emit_download_artifact,
    emit_pdf_artifact,
    emit_screenshot_artifact,
    emit_waited_download_artifact,
    record_artifact,
)
from shared.web_automation.debug_capture import emit_debug_capture_artifact, start_capture_session
from shared.web_automation.observe import (
    append_console_entry,
    read_console_entries,
    read_error_entries,
    read_request_entries,
)
from shared.web_automation.service_observe_artifacts_projection import (
    project_highlight_result,
    project_request_entries,
    project_trace_start_result,
    project_trace_start_reused_result,
    project_trace_stop_result,
)
from shared.web_automation.snapshot import build_snapshot
from shared.web_automation.types import BrowserArtifact, BrowserConsoleEntry, BrowserSnapshot


class BrowserServiceObserveArtifactsMixin:
    def snapshot(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        max_chars: int | None = None,
        max_refs: int | None = None,
    ) -> BrowserSnapshot | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        if self._is_live_mode():
            assert self._live_driver is not None
            snapshot = self._live_driver.snapshot_tab(
                tab,
                max_chars=max_chars or 4000,
                max_refs=max_refs or 50,
            )
            return snapshot
        snapshot = build_snapshot(tab, max_chars=max_chars or 4000, max_refs=max_refs or 50)
        self._persist_if_needed()
        return snapshot

    def console(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        level: str | None = None,
        limit: int | None = None,
    ) -> list[BrowserConsoleEntry] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        return read_console_entries(tab, level=level, limit=limit or 100)

    def errors(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        limit: int | None = None,
    ) -> list[BrowserConsoleEntry] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        return read_error_entries(tab, limit=limit or 100)

    def requests(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        limit: int | None = None,
        outcome: str | None = None,
        method: str | None = None,
    ) -> list[dict[str, object]] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        entries = read_request_entries(tab, limit=limit or 100, outcome=outcome, method=method)
        return project_request_entries(entries, fallback_url=tab.url)

    def screenshot(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        ref: str | None = None,
    ) -> BrowserArtifact | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        if self._is_live_mode():
            assert self._live_driver is not None
            return self._live_driver.screenshot_tab(tab, ref=ref)
        artifact = emit_screenshot_artifact(tab, ref=ref)
        self._persist_if_needed()
        return artifact

    def highlight(
        self,
        *,
        ref: str,
        target_id: str | None = None,
        profile: str | None = None,
        time_ms: int | None = None,
    ) -> dict[str, object] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        normalized_ref = str(ref or "").strip()
        target_ref = self._require_ref(tab, normalized_ref)
        duration_ms = max(80, int(time_ms or 500))
        artifact: BrowserArtifact
        mode = "synthetic_preview"
        if self._is_live_mode():
            assert self._live_driver is not None
            page = self._live_driver._pages.get(tab.tab_id)
            if page is None:
                raise ValueError(f"tab is not attached to a live page: {tab.tab_id}")
            locator = self._live_driver._locator_for_ref(tab, normalized_ref)
            highlight_state = locator.evaluate(
                """
                (el) => {
                  const previous = {
                    outline: el.style.outline || "",
                    outlineOffset: el.style.outlineOffset || "",
                    boxShadow: el.style.boxShadow || "",
                    transition: el.style.transition || "",
                  };
                  el.style.outline = "3px solid #ff6a00";
                  el.style.outlineOffset = "2px";
                  el.style.boxShadow = "0 0 0 4px rgba(255, 106, 0, 0.28)";
                  el.style.transition = "outline 80ms ease, box-shadow 80ms ease";
                  return previous;
                }
                """
            )
            try:
                page.wait_for_timeout(min(duration_ms, 250))
                artifact = self._live_driver.screenshot_tab(tab, ref=normalized_ref)
                mode = "live_overlay"
            finally:
                locator.evaluate(
                    """
                    (el, previous) => {
                      const source = previous && typeof previous === "object" ? previous : {};
                      el.style.outline = source.outline || "";
                      el.style.outlineOffset = source.outlineOffset || "";
                      el.style.boxShadow = source.boxShadow || "";
                      el.style.transition = source.transition || "";
                    }
                    """,
                    highlight_state,
                )
                self._live_driver._sync_tab(tab, page)
        else:
            artifact = emit_screenshot_artifact(tab, ref=normalized_ref)
        append_console_entry(
            tab,
            message_type="info",
            text=f"Highlighted ref {normalized_ref}",
            location={"url": tab.url, "ref": normalized_ref},
        )
        self._persist_if_needed()
        return project_highlight_result(
            tab=tab,
            target_ref=target_ref,
            normalized_ref=normalized_ref,
            mode=mode,
            duration_ms=duration_ms,
            artifact=artifact,
        )

    def pdf(
        self, *, target_id: str | None = None, profile: str | None = None
    ) -> BrowserArtifact | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        if self._is_live_mode():
            assert self._live_driver is not None
            return self._live_driver.pdf_tab(tab)
        artifact = emit_pdf_artifact(tab)
        self._persist_if_needed()
        return artifact

    def download(
        self,
        *,
        ref: str,
        target_id: str | None = None,
        profile: str | None = None,
        path: str | None = None,
    ) -> BrowserArtifact | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        normalized_ref = str(ref or "").strip()
        if not normalized_ref:
            raise ValueError("download requires ref")
        self._require_ref(tab, normalized_ref)
        if self._is_live_mode():
            assert self._live_driver is not None
            return self._live_driver.download_ref(tab, ref=normalized_ref, requested_path=path)
        artifact = emit_download_artifact(tab, ref=normalized_ref, requested_path=path)
        self._persist_if_needed()
        return artifact

    def wait_download(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        timeout_ms: int | None = None,
        path: str | None = None,
    ) -> BrowserArtifact | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        if self._is_live_mode():
            assert self._live_driver is not None
            return self._live_driver.wait_for_download(
                tab, timeout_ms=timeout_ms, requested_path=path
            )
        artifact = emit_waited_download_artifact(tab, requested_path=path)
        self._persist_if_needed()
        return artifact

    def trace_start(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
    ) -> dict[str, object] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        profile_name = tab.profile
        current = self._debug_sessions.get(profile_name)
        if current and current.get("status") == "active":
            current["target_id"] = tab.tab_id
            current["url"] = tab.url
            current["title"] = tab.title
            return project_trace_start_reused_result(tab=tab, session=current)
        mode = "debug_bundle"
        if self._is_live_mode():
            assert self._live_driver is not None
            context = self._live_driver._contexts.get(profile_name)
            if context is not None:
                try:
                    context.tracing.start(screenshots=True, snapshots=True, sources=False)
                    mode = "playwright_trace"
                except Exception:
                    mode = "debug_bundle"
        session = start_capture_session(
            profile=profile_name,
            target_id=tab.tab_id,
            url=tab.url,
            title=tab.title,
            mode=mode,
        )
        self._debug_sessions[profile_name] = session
        append_console_entry(
            tab,
            message_type="info",
            text=f"Started {mode} capture {session['trace_id']}",
            location={"url": tab.url},
        )
        self._persist_if_needed()
        return project_trace_start_result(tab=tab, session=session, mode=mode)

    def trace_stop(
        self,
        *,
        target_id: str | None = None,
        profile: str | None = None,
        path: str | None = None,
    ) -> dict[str, object] | None:
        tab = self._resolve_tab(target_id=target_id, profile=profile)
        if tab is None:
            return None
        profile_name = tab.profile
        session = self._debug_sessions.get(profile_name)
        if not session or session.get("status") != "active":
            raise ValueError("trace capture is not active")
        cookies = self.cookies(target_id=tab.tab_id, profile=profile_name) or []
        storage_state = self.storage_state(target_id=tab.tab_id, profile=profile_name) or {
            "origins": []
        }
        capture_mode = str(session.get("mode") or "debug_bundle").strip() or "debug_bundle"
        artifact: BrowserArtifact
        if capture_mode == "playwright_trace" and self._is_live_mode():
            assert self._live_driver is not None
            context = self._live_driver._contexts.get(profile_name)
            if context is None:
                artifact = emit_debug_capture_artifact(
                    tab,
                    session=session,
                    cookies=cookies,
                    storage_state=storage_state,
                    requested_path=path,
                )
                capture_mode = "debug_bundle"
            else:
                output_path = self._trace_output_path(
                    tab, trace_id=str(session["trace_id"]), requested_path=path
                )
                context.tracing.stop(path=str(output_path))
                artifact = record_artifact(
                    tab,
                    kind="trace",
                    path=output_path,
                    content_type="application/zip",
                    size_bytes=output_path.stat().st_size,
                    url=tab.url,
                    title=tab.title,
                    suggested_filename=output_path.name,
                )
        else:
            artifact = emit_debug_capture_artifact(
                tab,
                session=session,
                cookies=cookies,
                storage_state=storage_state,
                requested_path=path,
            )
        session["status"] = "stopped"
        session["stopped_at"] = artifact.created_at
        self._debug_sessions.pop(profile_name, None)
        append_console_entry(
            tab,
            message_type="info",
            text=f"Stopped {capture_mode} capture {session['trace_id']}",
            location={"url": tab.url},
        )
        self._persist_if_needed()
        return project_trace_stop_result(
            tab=tab,
            session=session,
            capture_mode=capture_mode,
            artifact=artifact,
        )
