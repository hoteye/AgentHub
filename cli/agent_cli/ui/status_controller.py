from __future__ import annotations

from cli.agent_cli.ui.status_controller_approval_runtime import (
    StatusControllerApprovalRuntimeMixin,
)
from cli.agent_cli.ui.status_controller_busy_runtime import (
    StatusControllerBusyRuntimeMixin,
)
from cli.agent_cli.ui.status_controller_preview_runtime import (
    StatusControllerPreviewRuntimeMixin,
)
from cli.agent_cli.ui.status_controller_projection_helpers import (
    StatusControllerProjectionHelpersMixin,
)
from cli.agent_cli.ui.status_controller_provider_runtime import (
    StatusControllerProviderRuntimeMixin,
)


class StatusControllerMixin(
    StatusControllerApprovalRuntimeMixin,
    StatusControllerBusyRuntimeMixin,
    StatusControllerProviderRuntimeMixin,
    StatusControllerPreviewRuntimeMixin,
    StatusControllerProjectionHelpersMixin,
):
    """Facade mixin for status controller behavior."""
