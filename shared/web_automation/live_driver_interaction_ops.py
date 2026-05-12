from __future__ import annotations

import time
from typing import Any


def click(self, tab, *, ref: str) -> dict[str, object]:
    self._run_ref_action(tab, ref, lambda locator: locator.click(timeout=self._interaction_timeout_ms()))
    self._settle_page(self._require_page(tab))
    self._sync_tab(tab, self._require_page(tab))
    return {
        "ok": True,
        "kind": "click",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Clicked ref {ref}",
    }


def double_click(self, tab, *, ref: str) -> dict[str, object]:
    self._run_ref_action(tab, ref, lambda locator: locator.dblclick(timeout=self._interaction_timeout_ms()))
    self._settle_page(self._require_page(tab))
    self._sync_tab(tab, self._require_page(tab))
    return {
        "ok": True,
        "kind": "double_click",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Double-clicked ref {ref}",
    }


def hover(self, tab, *, ref: str) -> dict[str, object]:
    self._run_ref_action(tab, ref, lambda locator: locator.hover(timeout=self._interaction_timeout_ms()))
    return {
        "ok": True,
        "kind": "hover",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Hovered ref {ref}",
    }


def scroll_into_view(self, tab, *, ref: str) -> dict[str, object]:
    self._run_ref_action(
        tab,
        ref,
        lambda locator: locator.scroll_into_view_if_needed(timeout=self._interaction_timeout_ms()),
    )
    return {
        "ok": True,
        "kind": "scroll_into_view",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Scrolled ref {ref} into view",
    }


def focus_ref(self, tab, *, ref: str) -> dict[str, object]:
    self._run_ref_action(tab, ref, lambda locator: locator.focus(timeout=self._interaction_timeout_ms()))
    return {
        "ok": True,
        "kind": "focus",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Focused ref {ref}",
    }


def type_text(self, tab, *, ref: str, text: str) -> dict[str, object]:
    normalized_text = str(text)

    def _fill(locator):
        try:
            locator.fill(normalized_text, timeout=self._interaction_timeout_ms())
        except Exception:
            locator.click(timeout=self._interaction_timeout_ms())
            locator.press("Control+A", timeout=self._interaction_timeout_ms())
            locator.type(normalized_text, delay=40, timeout=self._interaction_timeout_ms())

    self._run_ref_action(tab, ref, _fill)
    self._settle_page(self._require_page(tab), timeout_ms=1500)
    tab.input_state[ref] = normalized_text
    return {
        "ok": True,
        "kind": "type",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Typed into ref {ref}",
        "form_state": {ref: normalized_text},
    }


def clear_field(self, tab, *, ref: str) -> dict[str, object]:
    self._run_ref_action(tab, ref, lambda locator: locator.fill("", timeout=self._interaction_timeout_ms()))
    self._settle_page(self._require_page(tab), timeout_ms=1000)
    tab.input_state[ref] = ""
    return {
        "ok": True,
        "kind": "clear",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Cleared ref {ref}",
        "form_state": {ref: ""},
    }


def press_key(self, tab, *, key: str) -> dict[str, object]:
    page = self._require_page(tab)
    normalized_key = str(key).strip()
    if not normalized_key:
        raise ValueError("key is required")
    page.keyboard.press(normalized_key)
    self._settle_page(page, timeout_ms=1000)
    return {
        "ok": True,
        "kind": "press",
        "target_id": tab.tab_id,
        "url": tab.url,
        "message": f"Pressed key {normalized_key}",
        "result": {"key": normalized_key},
    }


def check(self, tab, *, ref: str) -> dict[str, object]:
    self._run_ref_action(tab, ref, lambda locator: locator.check(timeout=self._interaction_timeout_ms()))
    self._settle_page(self._require_page(tab), timeout_ms=1000)
    tab.input_state[ref] = "checked"
    return {
        "ok": True,
        "kind": "check",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Checked ref {ref}",
        "form_state": {ref: "checked"},
    }


def uncheck(self, tab, *, ref: str) -> dict[str, object]:
    self._run_ref_action(tab, ref, lambda locator: locator.uncheck(timeout=self._interaction_timeout_ms()))
    self._settle_page(self._require_page(tab), timeout_ms=1000)
    tab.input_state[ref] = "unchecked"
    return {
        "ok": True,
        "kind": "uncheck",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": f"Unchecked ref {ref}",
        "form_state": {ref: "unchecked"},
    }


def drag(self, tab, *, start_ref: str, end_ref: str) -> dict[str, object]:
    normalized_start = str(start_ref or "").strip()
    normalized_end = str(end_ref or "").strip()
    if not normalized_start or not normalized_end:
        raise ValueError("drag requires start_ref and end_ref")
    try:
        start_locator = self._locator_for_ref(tab, normalized_start)
        end_locator = self._locator_for_ref(tab, normalized_end)
        start_locator.drag_to(end_locator, timeout=self._interaction_timeout_ms())
    except Exception as exc:
        if self._should_retry_ref_action(exc):
            self._refresh_refs_for_tab(tab)
            try:
                start_locator = self._locator_for_ref(tab, normalized_start)
                end_locator = self._locator_for_ref(tab, normalized_end)
                start_locator.drag_to(end_locator, timeout=self._interaction_timeout_ms())
            except Exception as retry_exc:
                raise self._to_ai_friendly_error(retry_exc, f"{normalized_start}->{normalized_end}")
        else:
            raise self._to_ai_friendly_error(exc, f"{normalized_start}->{normalized_end}")
    self._settle_page(self._require_page(tab), timeout_ms=1000)
    return {
        "ok": True,
        "kind": "drag",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": normalized_start,
        "message": f"Dragged ref {normalized_start} to {normalized_end}",
        "result": {"start_ref": normalized_start, "end_ref": normalized_end},
    }


def resize_viewport(self, tab, *, width: int, height: int) -> dict[str, object]:
    page = self._require_page(tab)
    normalized_width = max(1, int(width))
    normalized_height = max(1, int(height))
    page.set_viewport_size({"width": normalized_width, "height": normalized_height})
    self._settle_page(page, timeout_ms=250)
    return {
        "ok": True,
        "kind": "resize",
        "target_id": tab.tab_id,
        "url": tab.url,
        "message": f"Resized viewport to {normalized_width}x{normalized_height}",
        "result": {"width": normalized_width, "height": normalized_height},
    }


def select_values(self, tab, *, ref: str, values: list[str]) -> dict[str, object]:
    normalized_values = [str(item).strip() for item in values if str(item).strip()]
    self._run_ref_action(
        tab,
        ref,
        lambda locator: locator.select_option(normalized_values, timeout=self._interaction_timeout_ms()),
    )
    self._settle_page(self._require_page(tab), timeout_ms=1500)
    tab.input_state[ref] = ",".join(normalized_values)
    return {
        "ok": True,
        "kind": "select",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "count": len(normalized_values),
        "message": f"Selected {len(normalized_values)} value(s) on ref {ref}",
        "form_state": {ref: tab.input_state[ref]},
        "result": {"values": normalized_values},
    }


def fill_fields(self, tab, *, fields: list[dict[str, Any]]) -> dict[str, object]:
    changed: dict[str, str] = {}
    normalized_fields: list[dict[str, str]] = []
    for item in fields:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        value = str(item.get("value") or "")
        if not ref:
            continue
        self._run_ref_action(tab, ref, lambda locator, field_value=value: locator.fill(field_value, timeout=self._interaction_timeout_ms()))
        changed[ref] = value
        normalized_fields.append({"ref": ref, "value": value})
        tab.input_state[ref] = value
    self._settle_page(self._require_page(tab), timeout_ms=1500)
    return {
        "ok": True,
        "kind": "fill",
        "target_id": tab.tab_id,
        "url": tab.url,
        "count": len(changed),
        "message": f"Filled {len(changed)} field(s)",
        "form_state": changed,
        "result": {"fields": normalized_fields},
    }


def wait_time(self, tab, *, time_ms: int) -> dict[str, object]:
    bounded = max(0, int(time_ms))
    time.sleep(bounded / 1000.0)
    return {
        "ok": True,
        "kind": "wait",
        "target_id": tab.tab_id,
        "url": tab.url,
        "message": f"Waited for {bounded}ms",
        "result": {"time_ms": bounded},
    }


def evaluate_script(self, tab, *, fn: str, ref: str | None = None) -> dict[str, object]:
    normalized_fn = str(fn or "").strip()
    if not normalized_fn:
        raise ValueError("evaluate requires fn")
    result_holder: dict[str, Any] = {}
    if ref:
        self._run_ref_action(
            tab,
            ref,
            lambda locator: result_holder.__setitem__("value", locator.evaluate(normalized_fn)),
        )
        message = f"Evaluated function on ref {ref}"
    else:
        page = self._require_page(tab)
        result_holder["value"] = page.evaluate(normalized_fn)
        message = "Evaluated function on page"
    page = self._require_page(tab)
    self._settle_page(page, timeout_ms=1000)
    self._sync_tab(tab, page)
    return {
        "ok": True,
        "kind": "evaluate",
        "target_id": tab.tab_id,
        "url": tab.url,
        "ref": ref,
        "message": message,
        "result": {"value": result_holder.get("value")},
    }


def bind_live_driver_interaction_ops(cls) -> None:
    for fn in (
        click,
        double_click,
        hover,
        scroll_into_view,
        focus_ref,
        type_text,
        clear_field,
        press_key,
        check,
        uncheck,
        drag,
        resize_viewport,
        select_values,
        fill_fields,
        wait_time,
        evaluate_script,
    ):
        setattr(cls, fn.__name__, fn)
