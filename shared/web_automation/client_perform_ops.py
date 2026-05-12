from __future__ import annotations


def _client_module():
    from shared.web_automation import client as client_module

    return client_module


def perform(
    self,
    *,
    action: str,
    profile: str | None = None,
    tab_id: str | None = None,
    url: str | None = None,
    ref: str | None = None,
    start_ref: str | None = None,
    end_ref: str | None = None,
    level: str | None = None,
    max_chars: int | None = None,
    max_refs: int | None = None,
    limit: int | None = None,
    outcome: str | None = None,
    method: str | None = None,
    storage_kind: str | None = None,
    path: str | None = None,
    kind: str | None = None,
    text: str | None = None,
    key: str | None = None,
    cookies: list[dict[str, object]] | None = None,
    items: dict[str, object] | None = None,
    values: list[str] | None = None,
    fields: list[dict[str, object]] | None = None,
    time_ms: int | None = None,
    width: int | None = None,
    height: int | None = None,
    paths: list[str] | None = None,
    input_ref: str | None = None,
    accept: bool | None = None,
    prompt_text: str | None = None,
    name: str | None = None,
    color: str | None = None,
    cdp_url: str | None = None,
    user_data_dir: str | None = None,
    driver: str | None = None,
    headless: bool | None = None,
    attach_only: bool | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    normalized = str(action or "").strip().lower()
    if normalized == "status":
        status = self.status()
        target_profile = str(profile or status.active_profile or "").strip() or status.active_profile
        profile_state = client_module._service.state.profiles.get(target_profile)
        spec = profile_state.spec if profile_state is not None else client_module._profile_spec(target_profile)
        connection_hints = client_module._service.connection_hints(profile=target_profile)
        return {
            "ok": True,
            "action": normalized,
            "profile": target_profile,
            "running": bool(profile_state.running) if profile_state is not None else False,
            "active_tab": profile_state.active_tab if profile_state is not None else None,
            "tabs": len(profile_state.tabs) if profile_state is not None else 0,
            "driver": str(getattr(spec, "driver", "") or ""),
            "mode": client_module._profile_mode(spec) if spec is not None else "",
            "transport": client_module._profile_transport(spec) if spec is not None else "",
            "cdp_url": str(getattr(spec, "cdp_url", "") or ""),
            "cdp_http": bool(connection_hints.get("cdp_http")),
            "cdp_ready": bool(connection_hints.get("cdp_ready")),
            "attach_only": bool(getattr(spec, "attach_only", False)),
        }
    if normalized == "start":
        return {
            "ok": self.start(profile=profile),
            "action": normalized,
            "profile": profile or client_module._service.state.default_profile,
        }
    if normalized == "stop":
        return {
            "ok": self.stop(profile=profile),
            "action": normalized,
            "profile": profile or client_module._service.state.default_profile,
        }
    if normalized == "profiles":
        profiles = self.profiles()
        return {
            "ok": True,
            "action": normalized,
            "profiles": profiles,
            "profile_names": [item["name"] for item in profiles],
            "count": len(profiles),
        }
    if normalized == "create_profile":
        spec = self.create_profile(
            name=str(name or "").strip(),
            color=color,
            cdp_url=cdp_url,
            user_data_dir=user_data_dir,
            driver=driver,
            headless=headless,
            attach_only=attach_only,
        )
        mode = client_module._profile_mode(spec)
        return {
            "ok": True,
            "action": normalized,
            "profile": spec.name,
            "transport": client_module._profile_transport(spec),
            "cdp_url": spec.cdp_url or None,
            "user_data_dir": spec.user_data_dir or None,
            "color": spec.color,
            "is_remote": mode == "remote-cdp",
            "driver": spec.driver,
            "attach_only": spec.attach_only,
        }
    if normalized == "delete_profile":
        profile_name = str(name or profile or "").strip()
        return {
            "ok": self.delete_profile(profile_name),
            "action": normalized,
            "profile": profile_name,
            "deleted": True,
        }
    if normalized == "reset_profile":
        result = self.reset_profile(profile=profile)
        return {
            "ok": True,
            "action": normalized,
            **result,
        }
    if normalized == "tabs":
        tabs = self.tabs(profile=profile)
        return {
            "ok": True,
            "action": normalized,
            "profile": profile or client_module._service.state.default_profile,
            "count": len(tabs),
            "tabs": [
                {"tab_id": tab.tab_id, "url": tab.url, "title": tab.title, "profile": tab.profile}
                for tab in tabs
            ],
        }
    if normalized == "open":
        tab = self.open(url=str(url or "").strip(), profile=profile)
        return client_module._tab_payload(normalized, tab, profile=profile, url=url)
    if normalized == "focus":
        ok = bool(tab_id) and self.focus(tab_id=str(tab_id), profile=profile)
        return {
            "ok": ok,
            "action": normalized,
            "profile": profile or client_module._service.state.default_profile,
            "target_id": tab_id,
        }
    if normalized == "close":
        ok = bool(tab_id) and self.close(tab_id=str(tab_id), profile=profile)
        return {
            "ok": ok,
            "action": normalized,
            "profile": profile or client_module._service.state.default_profile,
            "target_id": tab_id,
        }
    if normalized == "navigate":
        tab = self.navigate(url=str(url or "").strip(), profile=profile)
        return client_module._tab_payload(normalized, tab, profile=profile, url=url)
    if normalized == "snapshot":
        snapshot = self.snapshot(tab_id=tab_id, profile=profile, max_chars=max_chars, max_refs=max_refs)
        return client_module._snapshot_payload(normalized, snapshot, profile=profile, target_id=tab_id)
    if normalized == "console":
        entries = self.console(tab_id=tab_id, profile=profile, level=level, limit=limit)
        return client_module._console_payload(normalized, entries, profile=profile, target_id=tab_id)
    if normalized == "errors":
        entries = self.errors(tab_id=tab_id, profile=profile, limit=limit)
        return client_module._console_payload(normalized, entries, profile=profile, target_id=tab_id)
    if normalized == "requests":
        entries = self.requests(tab_id=tab_id, profile=profile, limit=limit, outcome=outcome, method=method)
        return client_module._request_payload(profile=profile, target_id=tab_id, entries=entries)
    if normalized == "screenshot":
        artifact = self.screenshot(tab_id=tab_id, profile=profile, ref=ref)
        return client_module._artifact_payload(normalized, artifact, profile=profile, target_id=tab_id)
    if normalized == "highlight":
        return self.highlight(tab_id=tab_id, profile=profile, ref=ref, time_ms=time_ms)
    if normalized == "pdf":
        artifact = self.pdf(tab_id=tab_id, profile=profile)
        return client_module._artifact_payload(normalized, artifact, profile=profile, target_id=tab_id)
    if normalized == "download":
        artifact = self.download(ref=str(ref or "").strip(), tab_id=tab_id, profile=profile, path=path)
        return client_module._artifact_payload(normalized, artifact, profile=profile, target_id=tab_id)
    if normalized == "wait_download":
        artifact = self.wait_download(tab_id=tab_id, profile=profile, timeout_ms=time_ms, path=path)
        return client_module._artifact_payload(normalized, artifact, profile=profile, target_id=tab_id)
    if normalized == "trace_start":
        return self.trace_start(tab_id=tab_id, profile=profile)
    if normalized == "trace_stop":
        return self.trace_stop(tab_id=tab_id, profile=profile, path=path)
    if normalized == "cookies":
        return self.cookies_payload(tab_id=tab_id, profile=profile)
    if normalized == "cookies_get":
        return self.get_cookies(tab_id=tab_id, profile=profile)
    if normalized == "cookies_set":
        return self.set_cookies(tab_id=tab_id, profile=profile, cookies=list(cookies or []))
    if normalized == "cookies_clear":
        return self.clear_cookies(tab_id=tab_id, profile=profile)
    if normalized == "storage_state":
        return self.storage_state_payload(tab_id=tab_id, profile=profile)
    if normalized == "storage_get":
        return self.get_storage(
            tab_id=tab_id,
            profile=profile,
            storage_kind=str(storage_kind or "").strip(),
        )
    if normalized == "storage_set":
        return self.set_storage(
            tab_id=tab_id,
            profile=profile,
            storage_kind=str(storage_kind or "").strip(),
            items=dict(items or {}),
        )
    if normalized == "storage_clear":
        return self.clear_storage(
            tab_id=tab_id,
            profile=profile,
            storage_kind=str(storage_kind or "").strip(),
        )
    if normalized == "act":
        return self.act(
            kind=str(kind or "").strip(),
            tab_id=tab_id,
            profile=profile,
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
        )
    if normalized == "upload":
        return self.upload(
            paths=list(paths or []),
            tab_id=tab_id,
            profile=profile,
            ref=ref,
            input_ref=input_ref,
            timeout_ms=time_ms,
        )
    if normalized == "dialog":
        return self.dialog(
            accept=True if accept is None else bool(accept),
            prompt_text=prompt_text,
            tab_id=tab_id,
            profile=profile,
            timeout_ms=time_ms,
        )
    raise ValueError(f"unsupported browser action: {action}")


def bind_browser_client_perform_ops(cls) -> None:
    setattr(cls, "perform", perform)
