from __future__ import annotations


class RuntimeKernelError(RuntimeError):
    """Base error for runtime kernel boundary failures."""


class RuntimeKernelUnavailableError(RuntimeKernelError):
    """Raised when a requested runtime kernel is not available."""


class RuntimeKernelSessionError(RuntimeKernelError):
    """Raised when a kernel cannot create, load, or operate on a session."""
