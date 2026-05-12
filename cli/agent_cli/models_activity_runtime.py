from __future__ import annotations

import json
from typing import Any, Dict


_LEGACY_ACTIVITY_TITLE_TO_CODE: Dict[str, str] = {
    "Execution interrupted": "interrupt.completed",
    "Applied patch": "patch.apply",
    "Patch apply failed": "patch.apply",
    "Created file": "patch.apply",
    "Overwrote file": "patch.apply",
    "Write failed": "patch.apply",
    "Requested patch approval": "approval.request.patch",
    "Patch approval request failed": "approval.request.patch",
    "Requested shell approval": "approval.request.shell",
    "Shell approval request failed": "approval.request.shell",
    "Requested background teammate approval": "approval.request.action",
    "Background teammate approval request failed": "approval.request.action",
    "Listed approvals": "approval.list",
    "Approval listing failed": "approval.list",
    "Approved patch": "approval.decision.patch",
    "Rejected patch": "approval.decision.patch",
    "Approved command": "approval.decision.command",
    "Rejected command": "approval.decision.command",
    "Approved action": "approval.decision.action",
    "Rejected action": "approval.decision.action",
    "Decided approval": "approval.decision",
    "Approval decision failed": "approval.decision",
    "Listed directory": "dir.list",
    "Directory listing failed": "dir.list",
    "Searched file paths": "dir.search",
    "File path search failed": "dir.search",
    "Read file": "file.read",
    "File read failed": "file.read",
    "Listed files": "file.list",
    "File listing failed": "file.list",
    "Searched files": "file.search",
    "File search failed": "file.search",
    "Listed visible conversations": "conversation.list",
    "Failed to list visible conversations": "conversation.list",
    "Analyzed visible attachments": "office.attachments.analyze",
    "Failed to analyze visible attachments": "office.attachments.analyze",
    "Listed office skills": "office.skills.list",
    "Failed to list office skills": "office.skills.list",
    "Searched the web": "web.search",
    "Web search failed": "web.search",
    "Native web search": "web.search",
    "Native web search failed": "web.search",
    "Local web search": "web.search",
    "Local web search failed": "web.search",
    "Viewed image": "image.view",
    "Viewed Image": "image.view",
    "View image failed": "image.view",
    "Fetched webpage": "web.fetch",
    "Webpage fetch failed": "web.fetch",
    "Opened webpage": "web.open",
    "Open webpage failed": "web.open",
    "Opened clicked link": "web.click",
    "Click failed": "web.click",
    "Found text in page": "web.find",
    "Find in page failed": "web.find",
    "Browser status": "browser.status",
    "Browser status failed": "browser.status",
    "Browser snapshot": "browser.snapshot",
    "Browser snapshot failed": "browser.snapshot",
    "Browser action": "browser.action",
    "Browser action failed": "browser.action",
    "Browser screenshot": "browser.screenshot",
    "Browser screenshot failed": "browser.screenshot",
    "Browser pdf": "browser.pdf",
    "Browser pdf failed": "browser.pdf",
    "Browser download": "browser.download",
    "Browser download failed": "browser.download",
    "Browser console": "browser.console",
    "Browser console failed": "browser.console",
    "Browser errors": "browser.errors",
    "Browser errors failed": "browser.errors",
    "Browser requests": "browser.requests",
    "Browser requests failed": "browser.requests",
    "Imported policy documents": "policy.import",
    "Failed to import policy documents": "policy.import",
    "Listed policy documents": "policy.list",
    "Failed to list policy documents": "policy.list",
    "Searched policy documents": "policy.search",
    "Failed to search policy documents": "policy.search",
    "Read policy Markdown": "policy.read",
    "Failed to read policy Markdown": "policy.read",
    "Initialized local toolchain": "bootstrap.initialize",
    "Initialization failed": "bootstrap.initialize",
    "Refreshed owner profile": "owner_profile.refresh",
    "Failed to refresh owner profile": "owner_profile.refresh",
    "Updated Plan": "plan.update",
    "Planned policy queries": "policy.plan",
    "Retrieved policy evidence": "policy.retrieve_evidence",
    "Bound evidence answer": "policy.bind_answer",
    "Verified policy answer": "policy.verify_answer",
    "Used native web search": "web.native_search",
    "Used local web search": "web.search",
    "Shell command completed": "command.run",
    "Shell input": "command.input",
    "Shell output": "command.output",
}


def activity_code(event: Any) -> str:
    code = str(getattr(event, "code", "") or "").strip()
    if code:
        return code
    title = str(getattr(event, "title", "") or "").strip()
    if not title:
        return ""
    explicit = _LEGACY_ACTIVITY_TITLE_TO_CODE.get(title)
    if explicit:
        return explicit
    if title.startswith("Interrupt requested for "):
        return "interrupt.requested"
    if title.startswith("Running "):
        running_subject = title[len("Running ") :].strip()
        if running_subject in {"list_dir", "file_list"}:
            return "dir.list" if running_subject == "list_dir" else "file.list"
        if running_subject in {"grep_files", "file_search"}:
            return "dir.search" if running_subject == "grep_files" else "file.search"
        if running_subject in {"read_file", "file_read"}:
            return "file.read"
        if str(getattr(event, "kind", "") or "").strip() == "command":
            return "command.run"
        return "tool.run"
    if title.startswith("Ran "):
        return "command.run"
    if title.startswith("Interrupted "):
        return "command.run"
    if title.startswith("Command failed: "):
        return "command.run"
    if title.startswith("Selected ") or title.startswith("Failed to select "):
        return "conversation.select"
    if title.startswith("Read recent messages from ") or title.startswith("Failed to read messages from "):
        return "conversation.read_recent"
    if title.startswith("Summarized ") or title.startswith("Failed to summarize "):
        return "conversation.summarize"
    if title.startswith("Drafted reply for ") or title.startswith("Failed to draft reply for "):
        return "conversation.draft_reply"
    if title.startswith("Prepared reply for ") or title.startswith("Prepare-send blocked for "):
        return "conversation.prepare_send"
    if title.startswith("Sent reply to ") or title.startswith("Send blocked for "):
        return "conversation.send_reply"
    if title.startswith("Ran ") or title.startswith("Failed to run "):
        return "office.skill.run"
    return ""


def _activity_params_json(event: Any) -> str:
    params = getattr(event, "params", None)
    if not isinstance(params, dict) or not params:
        return ""
    try:
        return json.dumps(params, ensure_ascii=False, sort_keys=True)
    except TypeError:
        normalized_items = sorted(
            ((str(key), repr(value)) for key, value in params.items()),
            key=lambda item: item[0],
        )
        return repr(normalized_items)


def activity_dedupe_key(event: Any) -> tuple[str, str, str, str, str]:
    code = activity_code(event)
    identity = code or str(getattr(event, "title", "") or "").strip()
    return (
        identity,
        str(getattr(event, "kind", "") or "").strip(),
        str(getattr(event, "status", "") or "").strip(),
        _activity_params_json(event),
        str(getattr(event, "detail", "") or ""),
    )
