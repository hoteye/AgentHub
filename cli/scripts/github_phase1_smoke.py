#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.agent_cli.runtime_factory import build_persistent_runtime
from plugins.github_phase1 import tools as github_tools


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        name = str(key).strip()
        if not name or name in os.environ:
            continue
        os.environ[name] = str(value).strip().strip('"').strip("'")


def _default_token_env() -> str:
    for name in ("GITHUB_TOKEN", "PM_GITHUB_TOKEN"):
        if str(os.environ.get(name) or "").strip():
            return name
    return "GITHUB_TOKEN"


def _json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _print_json(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2) + "\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GitHub Phase 1 smoke runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(action_parser: argparse.ArgumentParser) -> None:
        action_parser.add_argument("--token-env", default="")
        action_parser.add_argument("--api-base-url", default="https://api.github.com")
        action_parser.add_argument("--correlation-id", default="")
        action_parser.add_argument("--approve", action="store_true")
        action_parser.add_argument("--decided-by", default="github_phase1_smoke")
        action_parser.add_argument("--decision-note", default="")

    issue_create = subparsers.add_parser("issue-create")
    issue_create.add_argument("--repo", required=True)
    issue_create.add_argument("--title", required=True)
    issue_create.add_argument("--body", default="")
    add_common(issue_create)

    issue_comment = subparsers.add_parser("issue-comment")
    issue_comment.add_argument("--repo", required=True)
    issue_comment.add_argument("--issue-number", required=True, type=int)
    issue_comment.add_argument("--body", required=True)
    add_common(issue_comment)

    issue_labels = subparsers.add_parser("issue-add-labels")
    issue_labels.add_argument("--repo", required=True)
    issue_labels.add_argument("--issue-number", required=True, type=int)
    issue_labels.add_argument("--labels", required=True)
    add_common(issue_labels)

    issue_close = subparsers.add_parser("issue-close")
    issue_close.add_argument("--repo", required=True)
    issue_close.add_argument("--issue-number", required=True, type=int)
    add_common(issue_close)

    workflow_dispatch = subparsers.add_parser("workflow-dispatch")
    workflow_dispatch.add_argument("--repo", required=True)
    workflow_dispatch.add_argument("--workflow-id", required=True)
    workflow_dispatch.add_argument("--ref", required=True)
    workflow_dispatch.add_argument("--inputs-json", default="")
    add_common(workflow_dispatch)

    approval_list = subparsers.add_parser("approval-list")
    approval_list.add_argument("--status", default="")
    approval_list.add_argument("--limit", default=20, type=int)

    approval_approve = subparsers.add_parser("approval-approve")
    approval_approve.add_argument("--approval-id", required=True)
    approval_approve.add_argument("--decided-by", default="github_phase1_smoke")
    approval_approve.add_argument("--decision-note", default="")

    approval_reject = subparsers.add_parser("approval-reject")
    approval_reject.add_argument("--approval-id", required=True)
    approval_reject.add_argument("--decided-by", default="github_phase1_smoke")
    approval_reject.add_argument("--decision-note", default="")

    state = subparsers.add_parser("state")
    state.add_argument("--limit", default=20, type=int)

    return parser


def _split_repo(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if "/" not in text:
        raise ValueError("--repo must be <owner/repo>")
    owner, repo = text.split("/", 1)
    owner = owner.strip()
    repo = repo.strip()
    if not owner or not repo:
        raise ValueError("--repo must be <owner/repo>")
    return owner, repo


def _maybe_approve(runtime, event, args) -> dict[str, Any]:
    payload = {
        "requested": {
            "name": event.name,
            "ok": event.ok,
            "summary": event.summary,
            "payload": _json_safe(event.payload),
        },
    }
    approval_ticket = ((event.payload or {}).get("approval_ticket") or {})
    approval_id = str(approval_ticket.get("approval_id") or "").strip()
    if getattr(args, "approve", False) and approval_id:
        payload["approval_decision"] = runtime.decide_gateway_approval(
            approval_id,
            approved=True,
            decided_by=str(args.decided_by or "").strip() or "github_phase1_smoke",
            decision_note=str(args.decision_note or "").strip(),
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    _load_env_file(ROOT / ".env")
    parser = _build_parser()
    args = parser.parse_args(argv)
    runtime = build_persistent_runtime()

    if args.command == "state":
        return _print_json(runtime.gateway_state_snapshot(limit=int(args.limit)))
    if args.command == "approval-list":
        return _print_json(
            {
                "approval_tickets": runtime.list_approval_tickets(
                    limit=int(args.limit),
                    status=str(args.status or "").strip() or None,
                )
            }
        )
    if args.command == "approval-approve":
        return _print_json(
            runtime.decide_gateway_approval(
                args.approval_id,
                approved=True,
                decided_by=str(args.decided_by or "").strip() or "github_phase1_smoke",
                decision_note=str(args.decision_note or "").strip(),
            )
        )
    if args.command == "approval-reject":
        return _print_json(
            runtime.decide_gateway_approval(
                args.approval_id,
                approved=False,
                decided_by=str(args.decided_by or "").strip() or "github_phase1_smoke",
                decision_note=str(args.decision_note or "").strip(),
            )
        )

    owner, repo = _split_repo(args.repo)
    base_kwargs = {
        "token_env": str(args.token_env or "").strip() or _default_token_env(),
        "api_base_url": str(args.api_base_url or "").strip() or "https://api.github.com",
        "correlation_id": str(args.correlation_id or "").strip() or None,
        "runtime": runtime,
    }

    if args.command == "issue-create":
        event = github_tools.github_issue_create(
            owner=owner,
            repo=repo,
            title=args.title,
            body=args.body,
            **base_kwargs,
        )
        return _print_json(_maybe_approve(runtime, event, args))
    if args.command == "issue-comment":
        event = github_tools.github_issue_comment(
            owner=owner,
            repo=repo,
            issue_number=int(args.issue_number),
            body=args.body,
            **base_kwargs,
        )
        return _print_json(_maybe_approve(runtime, event, args))
    if args.command == "issue-add-labels":
        labels = [item.strip() for item in str(args.labels).split(",") if item.strip()]
        event = github_tools.github_issue_add_labels(
            owner=owner,
            repo=repo,
            issue_number=int(args.issue_number),
            labels=labels,
            **base_kwargs,
        )
        return _print_json(_maybe_approve(runtime, event, args))
    if args.command == "issue-close":
        event = github_tools.github_issue_close(
            owner=owner,
            repo=repo,
            issue_number=int(args.issue_number),
            **base_kwargs,
        )
        return _print_json(_maybe_approve(runtime, event, args))
    if args.command == "workflow-dispatch":
        inputs = json.loads(args.inputs_json) if args.inputs_json else {}
        if not isinstance(inputs, dict):
            raise ValueError("--inputs-json must decode to a JSON object")
        event = github_tools.github_workflow_dispatch(
            owner=owner,
            repo=repo,
            workflow_id=args.workflow_id,
            ref=args.ref,
            inputs=inputs,
            **base_kwargs,
        )
        return _print_json(_maybe_approve(runtime, event, args))

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
