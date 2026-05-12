from __future__ import annotations

from typing import Any, List

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_core import event_detail_rendering_helper_runtime as helper_runtime
from cli.agent_cli.runtime_core.tool_event_rendering import (
    append_elapsed_detail as _append_elapsed_detail,
    browser_activity_detail as _browser_activity_detail,
)


def render_activity_detail_for_event(event: ToolEvent) -> str:
    payload = event.payload or {}
    if event.name in {"web_search", "web_fetch", "open", "click", "find", "view_image"} and not event.ok:
        return str(payload.get("error") or f"{event.name} failed").strip()
    if event.name == "view_image":
        return helper_runtime.render_view_image_activity(payload)
    if event.name.startswith("browser"):
        return _browser_activity_detail(event)
    if event.name == "interrupted":
        return str(payload.get("reason") or "user_interrupt")
    if event.name in {"shell", "exec_command", "write_stdin"}:
        parts: List[str] = []
        returncode = payload.get("returncode")
        if returncode is not None:
            parts.append(f"exit {returncode}")
        duration_ms = payload.get("duration_ms")
        if duration_ms is not None:
            parts.append(f"{float(duration_ms) / 1000:.2f}s")
        if payload.get("interrupted"):
            parts.append("interrupted")
        if payload.get("timed_out"):
            parts.append("timed out")
        stdout = str(payload.get("stdout") or "").strip()
        stderr = str(payload.get("stderr") or "").strip()
        preview = stdout or stderr
        if not preview:
            parts.append("(no output)")
        summary = " | ".join(parts[:4])
        if event.ok or not stderr:
            return summary
        stderr_lines = [line.rstrip() for line in stderr.splitlines() if line.strip()]
        stderr_tail = stderr_lines[-3:]
        if not stderr_tail:
            return summary
        if not summary:
            summary = "command failed"
        first, *rest = stderr_tail
        rendered = [summary, f"stderr: {first}"]
        rendered.extend(rest)
        return "\n".join(rendered)
    if event.name == "apply_patch":
        return helper_runtime.render_apply_patch_activity(event)
    if event.name == "patch_approval_requested":
        return helper_runtime.render_patch_approval_requested_activity(event)
    if event.name == "shell_approval_requested":
        if not event.ok:
            return str(payload.get("error") or "shell approval request failed").strip()
        parts = [str(payload.get("approval_id") or "-")]
        command_text = str(payload.get("command") or "").strip()
        if command_text:
            parts.append(command_text)
        timeout_value = payload.get("timeout_sec")
        if timeout_value is not None:
            parts.append(f"timeout={int(timeout_value)}")
        return "\n".join(parts)
    if event.name.endswith("_approval_requested"):
        return helper_runtime.render_generic_approval_requested_activity(event)
    if event.name == "approval_list":
        return helper_runtime.render_approval_list_activity(event)
    if event.name == "approval_decision":
        return helper_runtime.render_approval_decision_activity(event)
    if event.name in {"glob_files", "file_list", "list_dir", "file_search", "grep_files", "file_read", "read_file"}:
        return helper_runtime.render_file_activity(event, append_elapsed_detail_fn=_append_elapsed_detail)
    if event.name == "list_conversations":
        selected = (payload.get("selected") or {}).get("name") or "-"
        count = payload.get("count") or 0
        return f"{count} visible, current {selected}"
    if event.name == "select_conversation":
        target = (payload.get("selected_after") or {}).get("name") or (payload.get("target") or {}).get("name") or "-"
        if event.ok:
            mode = payload.get("recovery_mode")
            return f"current {target}" + (f" via {mode}" if mode else "")
        return str(payload.get("reason") or payload.get("error") or "")
    if event.name == "read_recent_messages":
        lines = payload.get("recent_message_lines") or []
        return "\n".join(str(line) for line in lines[:4])
    if event.name == "summarize_conversation":
        return str(payload.get("summary_text") or "").strip()
    if event.name == "draft_reply":
        return str(payload.get("draft_reply") or "").strip()[:400]
    if event.name == "prepare_send":
        draft_text = str(payload.get("draft_text") or "").strip()
        risk_guard = payload.get("risk_guard") or {}
        parts = [draft_text[:300]] if draft_text else []
        if risk_guard.get("risk_level"):
            parts.append(f"risk {risk_guard['risk_level']}")
        return "\n".join(part for part in parts if part)
    if event.name == "send_reply":
        confirmed = bool(payload.get("confirmed"))
        return f"confirmed={confirmed}"
    if event.name == "download_and_understand_office_attachments":
        return str(payload.get("summary_text") or "").strip()[:400]
    if event.name == "policy_doc_import":
        return f"imported={int(payload.get('imported_count') or 0)}"
    if event.name == "policy_doc_list":
        return f"count={int(payload.get('count') or 0)}"
    if event.name in {"web_search", "web_fetch", "open", "click", "find"}:
        return helper_runtime.render_web_activity(
            event,
            append_elapsed_detail_fn=_append_elapsed_detail,
            first_excerpt_text_fn=first_excerpt_text,
        )
    if event.name == "policy_doc_search":
        return _append_elapsed_detail(f"count={int(payload.get('count') or 0)}", payload)
    if event.name == "policy_doc_read":
        document = payload.get("document") or {}
        parts = [str(document.get("doc_id") or "-")]
        if payload.get("truncated"):
            parts.append("truncated")
        return _append_elapsed_detail(" | ".join(parts), payload)
    return ""


def render_detail_for_event(event: ToolEvent) -> str:
    payload = event.payload or {}
    if event.name == "interrupted":
        return str(payload.get("reason") or "user_interrupt")
    if event.name == "list_conversations":
        selected = (payload.get("selected") or {}).get("name") or "-"
        return f"selected={selected}, count={payload.get('count') or 0}"
    if event.name == "select_conversation":
        target = (payload.get("selected_after") or {}).get("name") or (payload.get("target") or {}).get("name") or "-"
        if event.ok:
            detail = f"selected_conversation={target}"
            if payload.get("recovery_mode"):
                detail += f"\nrecovery_mode={payload['recovery_mode']}"
            return detail
        reason = str(payload.get("reason") or payload.get("error") or "-")
        return f"selected_conversation={target}, reason={reason}"
    if event.name == "read_recent_messages":
        lines = payload.get("recent_message_lines") or []
        return "\n".join(lines[:5])
    if event.name == "summarize_conversation":
        return str(payload.get("summary_text") or "").strip()
    if event.name == "draft_reply":
        return str(payload.get("draft_reply") or "").strip()
    if event.name == "prepare_send":
        return helper_runtime.render_prepare_send_detail(payload, draft_limit=600)
    if event.name == "send_reply":
        return helper_runtime.render_send_reply_detail(payload)
    if event.name == "download_and_understand_office_attachments":
        return str(payload.get("summary_text") or "").strip()
    if event.name == "policy_doc_import":
        parts = [f"imported_count={int(payload.get('imported_count') or 0)}"]
        documents = payload.get("documents") or []
        if documents:
            parts.append("doc_ids=" + ", ".join(str(item.get("doc_id")) for item in documents[:5]))
        errors = payload.get("errors") or []
        if errors:
            parts.append(f"errors={len(errors)}")
        return "\n".join(parts)
    if event.name == "apply_patch":
        return helper_runtime.render_apply_patch_detail(event)
    if event.name == "patch_approval_requested" or event.name.endswith("_approval_requested") or event.name in {"approval_list", "approval_decision"}:
        return helper_runtime.render_approval_detail(event)
    if event.name in {"glob_files", "file_list", "list_dir", "file_search", "grep_files", "file_read", "read_file"}:
        return helper_runtime.render_file_detail(event)
    if event.name == "policy_doc_list":
        documents = payload.get("documents") or []
        return "\n".join(f"{item.get('doc_id')} | {item.get('title')}" for item in documents[:10])
    if event.name in {"web_search", "view_image", "web_fetch", "open", "click", "find"}:
        return helper_runtime.render_web_detail(event, first_excerpt_text_fn=first_excerpt_text)
    if event.name == "policy_doc_search":
        documents = payload.get("documents") or []
        return "\n".join(
            f"{item.get('doc_id')} | {item.get('title')} | score={item.get('score')}"
            for item in documents[:10]
        )
    if event.name == "policy_doc_read":
        text = str(payload.get("text") or "").strip()
        document = payload.get("document") or {}
        prefix = f"doc_id={document.get('doc_id')}\n" if document else ""
        return prefix + text[:1200]
    return ""


def first_excerpt_text(payload: dict[str, Any]) -> str:
    excerpts = payload.get("excerpt_lines") or []
    if excerpts:
        text = str(excerpts[0].get("text") or "").strip()
        if text:
            return text
    plain_text = str(payload.get("text") or "").strip()
    if plain_text:
        return plain_text.splitlines()[0]
    return ""
