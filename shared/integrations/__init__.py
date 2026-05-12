"""Reusable integration primitives for gateway and plugin code."""

from .auth import (
    DEFAULT_SENSITIVE_HEADERS,
    apply_api_key_headers,
    build_basic_auth_header,
    build_bearer_auth_headers,
    merge_headers,
    redact_headers,
)
from .github_api import (
    build_github_issue_close_request,
    build_github_issue_comment_request,
    build_github_issue_create_request,
    build_github_issue_labels_request,
    build_github_workflow_dispatch_request,
    find_github_workflow_run,
    github_action_artifact_refs,
    github_delivery_id,
    github_request_target,
    github_repository_full_name,
    github_source_id,
    normalize_github_event_type,
)
from .http_client import HttpClient, HttpClientError, HttpRequest, HttpResponse
from .openapi_client import OpenAPIClient, OperationSpec
from .retry import RetryPolicy, retry_call
from .schemas import SchemaValidationError, coerce_str_mapping, ensure_mapping, pick_keys, require_keys
from .signatures import compute_hmac_sha256_hex, compute_sha256_hex, verify_hmac_sha256_hex

__all__ = [
    "DEFAULT_SENSITIVE_HEADERS",
    "HttpClient",
    "HttpClientError",
    "HttpRequest",
    "HttpResponse",
    "OpenAPIClient",
    "OperationSpec",
    "RetryPolicy",
    "SchemaValidationError",
    "apply_api_key_headers",
    "build_basic_auth_header",
    "build_bearer_auth_headers",
    "build_github_issue_close_request",
    "build_github_issue_comment_request",
    "build_github_issue_create_request",
    "build_github_issue_labels_request",
    "build_github_workflow_dispatch_request",
    "find_github_workflow_run",
    "coerce_str_mapping",
    "compute_hmac_sha256_hex",
    "compute_sha256_hex",
    "ensure_mapping",
    "github_action_artifact_refs",
    "github_delivery_id",
    "github_request_target",
    "github_repository_full_name",
    "github_source_id",
    "merge_headers",
    "normalize_github_event_type",
    "pick_keys",
    "redact_headers",
    "require_keys",
    "retry_call",
    "verify_hmac_sha256_hex",
]
