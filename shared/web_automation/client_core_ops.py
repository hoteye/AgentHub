from __future__ import annotations

from shared.web_automation.types import BrowserArtifact, BrowserConsoleEntry, BrowserSnapshot, BrowserStatus, BrowserTab


def _client_module():
    from shared.web_automation import client as client_module

    return client_module


def status(self) -> BrowserStatus:
    return _client_module()._service.status()


def start(self, profile: str | None = None) -> bool:
    return _client_module()._service.start(profile=profile)


def stop(self, profile: str | None = None) -> bool:
    return _client_module()._service.stop(profile=profile)


def profiles(self) -> list[dict[str, object]]:
    client_module = _client_module()
    return [
        {
            "name": spec.name,
            "color": spec.color,
            "driver": spec.driver,
            "mode": client_module._profile_mode(spec),
            "is_remote": client_module._profile_mode(spec) == "remote-cdp",
            "default": spec.default,
            "attach_only": spec.attach_only,
            "executable_path": spec.executable_path,
            "user_data_dir": spec.user_data_dir,
            "cdp_url": spec.cdp_url,
            "headless": spec.headless,
            "capabilities": client_module._profile_capabilities(spec),
        }
        for spec in client_module._service.list_profiles()
    ]


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
):
    return _client_module()._service.create_profile(
        name=name,
        color=color,
        cdp_url=cdp_url,
        user_data_dir=user_data_dir,
        driver=driver,
        headless=headless,
        attach_only=attach_only,
    )


def delete_profile(self, name: str) -> bool:
    return _client_module()._service.delete_profile(name)


def reset_profile(self, profile: str | None = None) -> dict[str, object]:
    return _client_module()._service.reset_profile(profile=profile)


def tabs(self, profile: str | None = None) -> list[BrowserTab]:
    return _client_module()._service.list_tabs(profile=profile)


def open(self, url: str, profile: str | None = None) -> BrowserTab | None:
    return _client_module()._service.open_tab(url, profile=profile)


def focus(self, tab_id: str, profile: str | None = None) -> bool:
    return _client_module()._service.focus_tab(tab_id, profile=profile)


def close(self, tab_id: str, profile: str | None = None) -> bool:
    return _client_module()._service.close_tab(tab_id, profile=profile)


def navigate(self, url: str, profile: str | None = None) -> BrowserTab | None:
    return _client_module()._service.navigate(url, profile=profile)


def snapshot(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
    max_chars: int | None = None,
    max_refs: int | None = None,
) -> BrowserSnapshot | None:
    return _client_module()._service.snapshot(
        target_id=tab_id,
        profile=profile,
        max_chars=max_chars,
        max_refs=max_refs,
    )


def console(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
    level: str | None = None,
    limit: int | None = None,
) -> list[BrowserConsoleEntry] | None:
    return _client_module()._service.console(target_id=tab_id, profile=profile, level=level, limit=limit)


def errors(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
    limit: int | None = None,
) -> list[BrowserConsoleEntry] | None:
    return _client_module()._service.errors(target_id=tab_id, profile=profile, limit=limit)


def requests(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
    limit: int | None = None,
    outcome: str | None = None,
    method: str | None = None,
) -> list[dict[str, object]] | None:
    return _client_module()._service.requests(
        target_id=tab_id,
        profile=profile,
        limit=limit,
        outcome=outcome,
        method=method,
    )


def screenshot(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
    ref: str | None = None,
) -> BrowserArtifact | None:
    return _client_module()._service.screenshot(target_id=tab_id, profile=profile, ref=ref)


def pdf(self, *, tab_id: str | None = None, profile: str | None = None) -> BrowserArtifact | None:
    return _client_module()._service.pdf(target_id=tab_id, profile=profile)


def highlight(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
    ref: str | None = None,
    time_ms: int | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.highlight(
        target_id=tab_id,
        profile=profile,
        ref=str(ref or "").strip(),
        time_ms=time_ms,
    )
    if result is None:
        return {
            "ok": False,
            "action": "highlight",
            "profile": profile or client_module._service.state.default_profile,
            "target_id": tab_id,
            "ref": ref,
        }
    payload = dict(result)
    payload.setdefault("profile", profile or client_module._service.state.default_profile)
    return payload


def download(
    self,
    *,
    ref: str,
    tab_id: str | None = None,
    profile: str | None = None,
    path: str | None = None,
) -> BrowserArtifact | None:
    return _client_module()._service.download(ref=ref, target_id=tab_id, profile=profile, path=path)


def wait_download(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
    timeout_ms: int | None = None,
    path: str | None = None,
) -> BrowserArtifact | None:
    return _client_module()._service.wait_download(
        target_id=tab_id,
        profile=profile,
        timeout_ms=timeout_ms,
        path=path,
    )


def trace_start(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.trace_start(target_id=tab_id, profile=profile)
    if result is None:
        return {
            "ok": False,
            "action": "trace_start",
            "profile": profile or client_module._service.state.default_profile,
            "target_id": tab_id,
        }
    payload = dict(result)
    payload.setdefault("profile", profile or client_module._service.state.default_profile)
    return payload


def trace_stop(
    self,
    *,
    tab_id: str | None = None,
    profile: str | None = None,
    path: str | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.trace_stop(target_id=tab_id, profile=profile, path=path)
    if result is None:
        return {
            "ok": False,
            "action": "trace_stop",
            "profile": profile or client_module._service.state.default_profile,
            "target_id": tab_id,
            "path": path,
        }
    payload = dict(result)
    payload.setdefault("profile", profile or client_module._service.state.default_profile)
    return payload


def bind_browser_client_core_ops(cls) -> None:
    for fn in (
        status,
        start,
        stop,
        profiles,
        create_profile,
        delete_profile,
        reset_profile,
        tabs,
        open,
        focus,
        close,
        navigate,
        snapshot,
        console,
        errors,
        requests,
        screenshot,
        pdf,
        highlight,
        download,
        wait_download,
        trace_start,
        trace_stop,
    ):
        setattr(cls, fn.__name__, fn)
