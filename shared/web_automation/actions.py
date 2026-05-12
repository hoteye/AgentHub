from __future__ import annotations

import ast
import re
from typing import Any

from shared.web_automation.hooks import consume_click_hooks
from shared.web_automation.observe import append_console_entry
from shared.web_automation.snapshot import ensure_tab_snapshot_seed, render_tab_text
from shared.web_automation.types import BrowserPageRef, BrowserTab

SUPPORTED_ACTION_KINDS = frozenset(
    {
        "click",
        "double_click",
        "type",
        "press",
        "hover",
        "scroll_into_view",
        "focus",
        "clear",
        "check",
        "uncheck",
        "drag",
        "resize",
        "select",
        "fill",
        "wait",
        "evaluate",
    }
)


def perform_tab_action(
    tab: BrowserTab,
    *,
    kind: str,
    ref: str | None = None,
    text: str | None = None,
    key: str | None = None,
    values: list[str] | None = None,
    fields: list[dict[str, Any]] | None = None,
    time_ms: int | None = None,
    start_ref: str | None = None,
    end_ref: str | None = None,
    width: int | None = None,
    height: int | None = None,
    evaluate_enabled: bool = False,
) -> dict[str, object]:
    ensure_tab_snapshot_seed(tab)
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in SUPPORTED_ACTION_KINDS:
        raise ValueError(f"unsupported browser act kind: {kind}")

    if normalized_kind == "click":
        target_ref = _require_ref(tab, ref)
        hook_messages = consume_click_hooks(tab, clicked_ref=target_ref.ref)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Clicked ref {target_ref.ref}",
            result={"hook_messages": hook_messages} if hook_messages else None,
        )

    if normalized_kind == "double_click":
        target_ref = _require_ref(tab, ref)
        hook_messages = consume_click_hooks(tab, clicked_ref=target_ref.ref)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Double-clicked ref {target_ref.ref}",
            result={"hook_messages": hook_messages} if hook_messages else None,
        )

    if normalized_kind == "hover":
        target_ref = _require_ref(tab, ref)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Hovered ref {target_ref.ref}",
        )

    if normalized_kind == "focus":
        target_ref = _require_ref(tab, ref)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Focused ref {target_ref.ref}",
        )

    if normalized_kind == "scroll_into_view":
        target_ref = _require_ref(tab, ref)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Scrolled ref {target_ref.ref} into view",
        )

    if normalized_kind == "press":
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("press requires key")
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            message=f"Pressed key {normalized_key}",
            result={"key": normalized_key},
        )

    if normalized_kind == "type":
        target_ref = _require_ref(tab, ref)
        typed_text = str(text or "")
        if not typed_text:
            raise ValueError("type requires text")
        existing = tab.input_state.get(target_ref.ref, "")
        tab.input_state[target_ref.ref] = f"{existing}{typed_text}"
        _refresh_tab_text(tab)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Typed into ref {target_ref.ref}",
            form_state={target_ref.ref: tab.input_state[target_ref.ref]},
        )

    if normalized_kind == "clear":
        target_ref = _require_ref(tab, ref)
        tab.input_state[target_ref.ref] = ""
        _refresh_tab_text(tab)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Cleared ref {target_ref.ref}",
            form_state={target_ref.ref: ""},
        )

    if normalized_kind == "check":
        target_ref = _require_ref(tab, ref)
        tab.input_state[target_ref.ref] = "checked"
        _refresh_tab_text(tab)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Checked ref {target_ref.ref}",
            form_state={target_ref.ref: "checked"},
        )

    if normalized_kind == "uncheck":
        target_ref = _require_ref(tab, ref)
        tab.input_state[target_ref.ref] = "unchecked"
        _refresh_tab_text(tab)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Unchecked ref {target_ref.ref}",
            form_state={target_ref.ref: "unchecked"},
        )

    if normalized_kind == "drag":
        drag_start = _require_ref(tab, start_ref or ref)
        drag_end = _require_ref(tab, end_ref or (values[0] if values else None))
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=drag_start.ref,
            message=f"Dragged ref {drag_start.ref} to {drag_end.ref}",
            result={"start_ref": drag_start.ref, "end_ref": drag_end.ref},
        )

    if normalized_kind == "resize":
        normalized_width = int(width or (values[0] if values else 0))
        normalized_height = int(height or (values[1] if values and len(values) > 1 else 0))
        if normalized_width <= 0 or normalized_height <= 0:
            raise ValueError("resize requires width and height")
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            message=f"Resized viewport to {normalized_width}x{normalized_height}",
            result={"width": normalized_width, "height": normalized_height, "simulated": True},
        )

    if normalized_kind == "select":
        target_ref = _require_ref(tab, ref)
        normalized_values = [str(item).strip() for item in (values or []) if str(item).strip()]
        if not normalized_values:
            raise ValueError("select requires values")
        tab.input_state[target_ref.ref] = ",".join(normalized_values)
        _refresh_tab_text(tab)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=target_ref.ref,
            message=f"Selected {len(normalized_values)} value(s) on ref {target_ref.ref}",
            form_state={target_ref.ref: tab.input_state[target_ref.ref]},
            count=len(normalized_values),
            result={"values": normalized_values},
        )

    if normalized_kind == "fill":
        normalized_fields = _normalize_fields(tab, fields)
        if not normalized_fields:
            raise ValueError("fill requires fields")
        changed: dict[str, str] = {}
        for item in normalized_fields:
            item_ref = item["ref"]
            item_value = item["value"]
            tab.input_state[item_ref] = item_value
            changed[item_ref] = item_value
        _refresh_tab_text(tab)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            message=f"Filled {len(changed)} field(s)",
            form_state=changed,
            count=len(changed),
            result={"fields": normalized_fields},
        )

    if normalized_kind == "wait":
        if time_ms is not None and int(time_ms) < 0:
            raise ValueError("wait time_ms must be non-negative")
        waited_ms = int(time_ms or 0)
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            message=f"Waited for {waited_ms}ms",
            result={"time_ms": waited_ms, "simulated": True},
        )

    if normalized_kind == "evaluate":
        if not evaluate_enabled:
            raise ValueError("browser evaluate is disabled by config (browser.evaluate_enabled=false)")
        result_value = _evaluate_synthetic(tab, fn=text, ref=ref)
        message = f"Evaluated function on ref {ref}" if ref else "Evaluated function on page"
        return _emit_action_result(
            tab,
            kind=normalized_kind,
            ref=ref,
            message=message,
            result={"value": result_value, "simulated": True},
        )

    raise ValueError(f"unsupported browser act kind: {kind}")


def _normalize_fields(tab: BrowserTab, fields: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in fields or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        value = str(item.get("value") or "")
        if not ref:
            continue
        _require_ref(tab, ref)
        normalized.append({"ref": ref, "value": value})
    return normalized


def _require_ref(tab: BrowserTab, ref: str | None) -> BrowserPageRef:
    normalized_ref = str(ref or "").strip()
    if not normalized_ref:
        raise ValueError("action requires ref")
    for item in tab.refs:
        if item.ref == normalized_ref:
            return item
    raise ValueError(f"unknown ref: {normalized_ref}")


def _refresh_tab_text(tab: BrowserTab) -> None:
    tab.text = render_tab_text(tab)


def _evaluate_synthetic(tab: BrowserTab, *, fn: str | None, ref: str | None) -> object:
    source = str(fn or "").strip()
    if not source:
        raise ValueError("evaluate requires fn")
    expr = _extract_eval_expression(source)
    if not expr:
        raise ValueError("evaluate requires fn")
    compact = re.sub(r"\s+", "", expr)
    target_ref = _require_ref(tab, ref) if ref else None

    if compact in {"document.title", "window.document.title"}:
        return tab.title
    if compact in {"window.location.href", "document.location.href", "location.href", "document.URL"}:
        return tab.url
    if compact in {"document.body.innerText", "document.body.textContent"}:
        return tab.text

    if target_ref is not None:
        if compact in {"el.textContent", "el.innerText", "el.innerHTML"}:
            return target_ref.name or ""
        if compact in {"el.href", "el.getAttribute('href')", 'el.getAttribute("href")'}:
            return target_ref.url or ""
        if compact == "el.value":
            return tab.input_state.get(target_ref.ref, "")
        if compact in {"el.ariaLabel", "el.getAttribute('aria-label')", 'el.getAttribute("aria-label")'}:
            return target_ref.name or ""

    literal = _parse_eval_literal(expr)
    if literal is not _UNSET:
        return literal

    scope = "ref" if target_ref is not None else "page"
    raise ValueError(f"synthetic evaluate only supports safe {scope} inspection helpers")


def _extract_eval_expression(source: str) -> str:
    text = str(source or "").strip()
    if not text:
        return ""
    if "=>" not in text:
        return text
    _head, _sep, tail = text.partition("=>")
    expression = tail.strip()
    if expression.startswith("{") and expression.endswith("}"):
        match = re.fullmatch(r"\{\s*return\s+(.+?)\s*;?\s*\}", expression, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
    return expression


_UNSET = object()


def _parse_eval_literal(expression: str) -> object:
    raw = str(expression or "").strip()
    compact = re.sub(r"\s+", "", raw)
    if compact == "true":
        return True
    if compact == "false":
        return False
    if compact == "null":
        return None
    if re.fullmatch(r"[-+]?\d+", compact):
        return int(compact)
    if re.fullmatch(r"[-+]?\d+\.\d+", compact):
        return float(compact)
    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        try:
            return ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return _UNSET
    return _UNSET


def _emit_action_result(
    tab: BrowserTab,
    *,
    kind: str,
    message: str,
    ref: str | None = None,
    form_state: dict[str, str] | None = None,
    count: int | None = None,
    result: dict[str, object] | None = None,
) -> dict[str, object]:
    append_console_entry(
        tab,
        message_type="info",
        text=message,
        location={"url": tab.url},
    )
    payload: dict[str, object] = {
        "ok": True,
        "kind": kind,
        "target_id": tab.tab_id,
        "url": tab.url,
        "message": message,
    }
    if ref:
        payload["ref"] = ref
    if form_state:
        payload["form_state"] = dict(form_state)
    if count is not None:
        payload["count"] = int(count)
    if result:
        payload["result"] = dict(result)
    return payload
