from __future__ import annotations

from cli.agent_cli.runtime_kernels.errors import RuntimeKernelError


class CodexSidecarError(RuntimeKernelError):
    """Base error for Codex ref sidecar integration failures."""


class CodexSidecarProcessError(CodexSidecarError):
    """Raised when the sidecar process cannot be started or exits unexpectedly."""


class CodexSidecarProtocolError(CodexSidecarError):
    """Raised when the sidecar emits invalid JSON-RPC data."""


class CodexSidecarRequestError(CodexSidecarError):
    """Raised when a sidecar JSON-RPC request fails or times out."""
