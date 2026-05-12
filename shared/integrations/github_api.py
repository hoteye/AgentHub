from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse

from .auth import build_bearer_auth_headers, merge_headers
from .http_client import HttpClient


def github_repository_full_name(payload: Mapping[str, Any]) -> str:
    repository = payload.get("repository")
    if isinstance(repository, Mapping):
        full_name = str(repository.get("full_name") or "").strip()
        if full_name:
            return full_name
    owner = ""
    name = ""
    if isinstance(repository, Mapping):
        owner_block = repository.get("owner")
        if isinstance(owner_block, Mapping):
            owner = str(owner_block.get("login") or owner_block.get("name") or "").strip()
        name = str(repository.get("name") or "").strip()
    if owner and name:
        return f"{owner}/{name}"
    return "unknown/unknown"


def github_source_id(payload: Mapping[str, Any]) -> str:
    return f"github:{github_repository_full_name(payload)}"


def normalize_github_event_type(
    *,
    headers: Optional[Mapping[str, Any]],
    payload: Mapping[str, Any],
) -> str:
    event_name = ""
    for key, value in (headers or {}).items():
        if str(key or "").strip().lower() == "x-github-event":
            event_name = str(value or "").strip().lower()
            break
    if not event_name:
        raise ValueError("X-GitHub-Event header is required")
    action = str(payload.get("action") or "").strip().lower()
    if event_name == "ping":
        return "github.ping"
    if action:
        return f"github.{event_name}.{action}"
    return f"github.{event_name}"


def github_delivery_id(headers: Optional[Mapping[str, Any]]) -> Optional[str]:
    for key, value in (headers or {}).items():
        if str(key or "").strip().lower() == "x-github-delivery":
            text = str(value or "").strip()
            return text or None
    return None


def _github_default_headers() -> Dict[str, str]:
    return merge_headers(
        {
            "Accept": "application/vnd.github+json",
            "User-Agent": "AgentHub-GitHub-Phase1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _allowed_host(api_base_url: str) -> str:
    parsed = urlparse(str(api_base_url or "").strip())
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("api_base_url must include a hostname")
    return host


def _repo_issue_html_url(owner: str, repo: str, issue_number: int) -> str:
    return f"https://github.com/{owner}/{repo}/issues/{int(issue_number)}"


def github_request_target(request_payload: Mapping[str, Any]) -> Dict[str, Any]:
    parameters = request_payload.get("parameters")
    if not isinstance(parameters, Mapping):
        return {}
    url = str(parameters.get("url") or "").strip()
    if not url:
        return {}
    parsed = urlparse(url)
    parts = [item for item in parsed.path.split("/") if item]
    if len(parts) < 4 or parts[0] != "repos":
        return {}
    owner = parts[1]
    repo = parts[2]
    target: Dict[str, Any] = {"owner": owner, "repo": repo, "url": url}
    if len(parts) >= 5 and parts[3] == "issues":
        try:
            issue_number = int(parts[4])
        except ValueError:
            issue_number = None
        if issue_number is not None:
            target["issue_number"] = issue_number
        if len(parts) >= 6 and parts[5] == "comments":
            target["target_kind"] = "issue_comment"
        elif len(parts) >= 6 and parts[5] == "labels":
            target["target_kind"] = "issue_labels"
        else:
            target["target_kind"] = "issue"
    elif len(parts) >= 7 and parts[3] == "actions" and parts[4] == "workflows":
        target["target_kind"] = "workflow_dispatch"
        target["workflow_id"] = parts[5]
    return target


def github_action_artifact_refs(
    *,
    action_type: str,
    request_payload: Mapping[str, Any],
    action_output: Mapping[str, Any],
) -> Dict[str, Any]:
    refs: list[str] = []
    details: Dict[str, Any] = {}
    target = github_request_target(request_payload)
    json_data = action_output.get("json_data")
    if action_type == "github.issue.create" and isinstance(json_data, Mapping):
        html_url = str(json_data.get("html_url") or "").strip()
        if html_url:
            refs.append(html_url)
            details["issue_url"] = html_url
        if json_data.get("number") is not None:
            details["issue_number"] = int(json_data["number"])
    elif action_type == "github.issue.comment" and isinstance(json_data, Mapping):
        html_url = str(json_data.get("html_url") or "").strip()
        if html_url:
            refs.append(html_url)
            details["comment_url"] = html_url
    elif action_type == "github.issue.labels.add":
        owner = str(target.get("owner") or "").strip()
        repo = str(target.get("repo") or "").strip()
        issue_number = target.get("issue_number")
        if owner and repo and issue_number is not None:
            issue_url = _repo_issue_html_url(owner, repo, int(issue_number))
            refs.append(issue_url)
            details["issue_url"] = issue_url
            details["issue_number"] = int(issue_number)
        if isinstance(json_data, list):
            details["labels"] = [
                str(item.get("name") or "").strip()
                for item in json_data
                if isinstance(item, Mapping) and str(item.get("name") or "").strip()
            ]
    elif action_type == "github.issue.close" and isinstance(json_data, Mapping):
        html_url = str(json_data.get("html_url") or "").strip()
        if html_url:
            refs.append(html_url)
            details["issue_url"] = html_url
        state = str(json_data.get("state") or "").strip()
        if state:
            details["state"] = state
    return {
        "artifact_refs": refs,
        "details": details,
    }


def find_github_workflow_run(
    *,
    request_payload: Mapping[str, Any],
    trace_id: str,
    occurred_after: str | None = None,
    http_client: HttpClient | None = None,
    max_attempts: int = 10,
) -> Dict[str, Any] | None:
    parameters = request_payload.get("parameters")
    if not isinstance(parameters, Mapping):
        return None
    auth = parameters.get("auth")
    if not isinstance(auth, Mapping):
        return None
    token_env = str(auth.get("token_env") or "").strip()
    if not token_env:
        return None
    token = str(__import__("os").environ.get(token_env) or "").strip()
    if not token:
        return None
    target = github_request_target(request_payload)
    owner = str(target.get("owner") or "").strip()
    repo = str(target.get("repo") or "").strip()
    workflow_id = str(target.get("workflow_id") or "").strip()
    if not owner or not repo or not workflow_id:
        return None
    query: Dict[str, Any] = {"event": "workflow_dispatch", "per_page": 10}
    json_body = parameters.get("json_body")
    if isinstance(json_body, Mapping):
        ref = str(json_body.get("ref") or "").strip()
        if ref:
            query["branch"] = ref
    client = http_client or HttpClient()
    headers = merge_headers(
        build_bearer_auth_headers(token),
        {
            "Accept": "application/vnd.github+json",
            "User-Agent": "AgentHub-GitHub-Phase1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    earliest = None
    if occurred_after:
        try:
            earliest = datetime.fromisoformat(str(occurred_after).replace("Z", "+00:00"))
        except ValueError:
            earliest = None
    for _ in range(max(1, int(max_attempts))):
        response = client.request_json(
            "GET",
            f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs",
            headers=headers,
            query=query,
            timeout_seconds=20.0,
            expected_statuses=(200,),
        )
        payload = response.json_data if isinstance(response.json_data, Mapping) else {}
        runs = payload.get("workflow_runs") if isinstance(payload, Mapping) else None
        if not isinstance(runs, list):
            runs = []
        for item in runs:
            if not isinstance(item, Mapping):
                continue
            display_title = str(item.get("display_title") or "").strip()
            run_started_at = str(item.get("run_started_at") or item.get("created_at") or "").strip()
            if trace_id and trace_id not in display_title:
                continue
            if earliest is not None and run_started_at:
                try:
                    started = datetime.fromisoformat(run_started_at.replace("Z", "+00:00"))
                except ValueError:
                    started = None
                if started is not None and started < earliest:
                    continue
            return {
                "run_id": item.get("id"),
                "run_number": item.get("run_number"),
                "html_url": item.get("html_url"),
                "display_title": display_title or None,
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
            }
        __import__("time").sleep(2.0)
    return None


def _build_http_action_request(
    *,
    method: str,
    url: str,
    token_env: str,
    json_body: Any,
    expected_statuses: list[int],
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "action": "http_request",
        "parameters": {
            "method": method,
            "url": url,
            "allowed_hosts": [_allowed_host(url)],
            "headers": _github_default_headers(),
            "auth": {
                "type": "bearer_env",
                "token_env": str(token_env or "GITHUB_TOKEN").strip() or "GITHUB_TOKEN",
            },
            "json_body": json_body,
            "expected_statuses": [int(item) for item in expected_statuses],
            "timeout_seconds": 20.0,
        },
        "correlation_id": str(correlation_id or "").strip() or None,
    }


def build_github_issue_create_request(
    *,
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _build_http_action_request(
        method="POST",
        url=f"{str(api_base_url).rstrip('/')}/repos/{owner}/{repo}/issues",
        token_env=token_env,
        json_body={"title": title, "body": body},
        expected_statuses=[201],
        correlation_id=correlation_id,
    )


def build_github_issue_comment_request(
    *,
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _build_http_action_request(
        method="POST",
        url=f"{str(api_base_url).rstrip('/')}/repos/{owner}/{repo}/issues/{int(issue_number)}/comments",
        token_env=token_env,
        json_body={"body": body},
        expected_statuses=[201],
        correlation_id=correlation_id,
    )


def build_github_issue_labels_request(
    *,
    owner: str,
    repo: str,
    issue_number: int,
    labels: list[str],
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _build_http_action_request(
        method="POST",
        url=f"{str(api_base_url).rstrip('/')}/repos/{owner}/{repo}/issues/{int(issue_number)}/labels",
        token_env=token_env,
        json_body={"labels": list(labels)},
        expected_statuses=[200],
        correlation_id=correlation_id,
    )


def build_github_issue_close_request(
    *,
    owner: str,
    repo: str,
    issue_number: int,
    token_env: str = "GITHUB_TOKEN",
    api_base_url: str = "https://api.github.com",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _build_http_action_request(
        method="PATCH",
        url=f"{str(api_base_url).rstrip('/')}/repos/{owner}/{repo}/issues/{int(issue_number)}",
        token_env=token_env,
        json_body={"state": "closed"},
        expected_statuses=[200],
        correlation_id=correlation_id,
    )


def build_github_workflow_dispatch_request(
    *,
    owner: str,
    repo: str,
    workflow_id: str,
    ref: str,
    token_env: str = "GITHUB_TOKEN",
    inputs: Optional[Dict[str, Any]] = None,
    api_base_url: str = "https://api.github.com",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _build_http_action_request(
        method="POST",
        url=f"{str(api_base_url).rstrip('/')}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
        token_env=token_env,
        json_body={"ref": ref, "inputs": dict(inputs or {})},
        expected_statuses=[204],
        correlation_id=correlation_id,
    )
