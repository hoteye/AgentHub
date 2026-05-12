from __future__ import annotations

from shared.web_automation.types import BrowserConsoleEntry


def _client_module():
    from shared.web_automation import client as client_module

    return client_module


def cookies(self, *, tab_id: str | None = None, profile: str | None = None) -> list[dict[str, object]] | None:
    return _client_module()._service.cookies(target_id=tab_id, profile=profile)


def get_cookies(self, *, tab_id: str | None = None, profile: str | None = None) -> dict[str, object]:
    client_module = _client_module()
    resolved_target = client_module._resolve_client_target_id(tab_id=tab_id, profile=profile)
    cookies = client_module._service.get_cookies(target_id=tab_id, profile=profile)
    return {
        "ok": True,
        "action": "cookies_get",
        "profile": profile or client_module._service.state.default_profile,
        "target_id": resolved_target,
        "count": len(cookies),
        "cookies": [dict(item) for item in cookies],
    }


def set_cookies(
    self,
    *,
    cookies: list[dict[str, object]],
    tab_id: str | None = None,
    profile: str | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.set_cookies(target_id=tab_id, profile=profile, cookies=cookies)
    return {
        "ok": True,
        "action": "cookies_set",
        "profile": profile or client_module._service.state.default_profile,
        "target_id": result.get("target_id") or client_module._resolve_client_target_id(tab_id=tab_id, profile=profile),
        "count": int(result.get("count") or 0),
        "cookies": [dict(item) for item in list(result.get("cookies") or []) if isinstance(item, dict)],
    }


def clear_cookies(self, *, tab_id: str | None = None, profile: str | None = None) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.clear_cookies(target_id=tab_id, profile=profile)
    return {
        "ok": True,
        "action": "cookies_clear",
        "profile": profile or client_module._service.state.default_profile,
        "target_id": result.get("target_id") or client_module._resolve_client_target_id(tab_id=tab_id, profile=profile),
        "cleared": int(result.get("cleared") or 0),
    }


def cookies_payload(self, *, tab_id: str | None = None, profile: str | None = None) -> dict[str, object]:
    client_module = _client_module()
    cookies = self.cookies(tab_id=tab_id, profile=profile)
    resolved_target = client_module._resolve_client_target_id(tab_id=tab_id, profile=profile)
    if cookies is None:
        return {
            "ok": False,
            "action": "cookies",
            "profile": profile or client_module._service.state.default_profile,
            "target_id": resolved_target,
        }
    return {
        "ok": True,
        "action": "cookies",
        "profile": profile or client_module._service.state.default_profile,
        "target_id": resolved_target,
        "count": len(cookies),
        "cookies": [dict(item) for item in cookies],
    }


def storage_state(self, *, tab_id: str | None = None, profile: str | None = None) -> dict[str, object] | None:
    return _client_module()._service.storage_state(target_id=tab_id, profile=profile)


def get_storage(
    self,
    *,
    storage_kind: str,
    tab_id: str | None = None,
    profile: str | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    items = client_module._service.get_storage(target_id=tab_id, profile=profile, storage_kind=storage_kind)
    return {
        "ok": True,
        "action": "storage_get",
        "profile": profile or client_module._service.state.default_profile,
        "target_id": client_module._resolve_client_target_id(tab_id=tab_id, profile=profile),
        "storage_kind": str(storage_kind or "").strip().lower(),
        "items": dict(items),
    }


def set_storage(
    self,
    *,
    storage_kind: str,
    items: dict[str, object],
    tab_id: str | None = None,
    profile: str | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.set_storage(
        target_id=tab_id,
        profile=profile,
        storage_kind=storage_kind,
        items=items,
    )
    return {
        "ok": True,
        "action": "storage_set",
        "profile": profile or client_module._service.state.default_profile,
        "target_id": result.get("target_id") or client_module._resolve_client_target_id(tab_id=tab_id, profile=profile),
        "storage_kind": str(result.get("storage_kind") or str(storage_kind or "").strip().lower()),
        "count": int(result.get("count") or 0),
        "items": dict(result.get("items") or {}),
    }


def clear_storage(
    self,
    *,
    storage_kind: str,
    tab_id: str | None = None,
    profile: str | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.clear_storage(target_id=tab_id, profile=profile, storage_kind=storage_kind)
    return {
        "ok": True,
        "action": "storage_clear",
        "profile": profile or client_module._service.state.default_profile,
        "target_id": result.get("target_id") or client_module._resolve_client_target_id(tab_id=tab_id, profile=profile),
        "storage_kind": str(result.get("storage_kind") or str(storage_kind or "").strip().lower()),
        "cleared": int(result.get("cleared") or 0),
    }


def storage_state_payload(self, *, tab_id: str | None = None, profile: str | None = None) -> dict[str, object]:
    client_module = _client_module()
    storage_state = self.storage_state(tab_id=tab_id, profile=profile)
    resolved_target = client_module._resolve_client_target_id(tab_id=tab_id, profile=profile)
    if storage_state is None:
        return {
            "ok": False,
            "action": "storage_state",
            "profile": profile or client_module._service.state.default_profile,
            "target_id": resolved_target,
        }
    return {
        "ok": True,
        "action": "storage_state",
        "profile": profile or client_module._service.state.default_profile,
        "target_id": resolved_target,
        "storage_state": dict(storage_state),
        "count": len(list(storage_state.get("origins") or [])),
    }


def act(
    self,
    *,
    kind: str,
    tab_id: str | None = None,
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
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.act(
        kind=kind,
        target_id=tab_id,
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
    if result is None:
        return {
            "ok": False,
            "kind": kind,
            "profile": profile or client_module._service.state.default_profile,
            "target_id": tab_id,
            "ref": ref,
            "start_ref": start_ref,
            "end_ref": end_ref,
        }
    payload = dict(result)
    payload.setdefault("profile", profile or client_module._service.state.default_profile)
    return payload


def upload(
    self,
    *,
    paths: list[str],
    tab_id: str | None = None,
    profile: str | None = None,
    ref: str | None = None,
    input_ref: str | None = None,
    timeout_ms: int | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.upload(
        paths=paths,
        target_id=tab_id,
        profile=profile,
        ref=ref,
        input_ref=input_ref,
        timeout_ms=timeout_ms,
    )
    if result is None:
        return {
            "ok": False,
            "action": "upload",
            "profile": profile or client_module._service.state.default_profile,
            "target_id": tab_id,
            "ref": ref,
            "input_ref": input_ref,
        }
    payload = dict(result)
    payload.setdefault("profile", profile or client_module._service.state.default_profile)
    return payload


def dialog(
    self,
    *,
    accept: bool = True,
    prompt_text: str | None = None,
    tab_id: str | None = None,
    profile: str | None = None,
    timeout_ms: int | None = None,
) -> dict[str, object]:
    client_module = _client_module()
    result = client_module._service.dialog(
        accept=accept,
        prompt_text=prompt_text,
        target_id=tab_id,
        profile=profile,
        timeout_ms=timeout_ms,
    )
    if result is None:
        return {
            "ok": False,
            "action": "dialog",
            "profile": profile or client_module._service.state.default_profile,
            "target_id": tab_id,
            "accept": accept,
        }
    payload = dict(result)
    payload.setdefault("profile", profile or client_module._service.state.default_profile)
    return payload


def bind_browser_client_state_ops(cls) -> None:
    for fn in (
        cookies,
        get_cookies,
        set_cookies,
        clear_cookies,
        cookies_payload,
        storage_state,
        get_storage,
        set_storage,
        clear_storage,
        storage_state_payload,
        act,
        upload,
        dialog,
    ):
        setattr(cls, fn.__name__, fn)
