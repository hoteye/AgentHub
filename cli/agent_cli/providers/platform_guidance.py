from __future__ import annotations

from cli.agent_cli.host_platform import HostPlatform


def structured_directory_snapshot_guidance(host_platform: HostPlatform) -> str:
    del host_platform
    return (
        "For a direct one-layer directory snapshot requested by the user, "
        "prefer list_dir with depth 1 over shell directory listings so the transcript "
        "stays structured and cross-platform. "
    )


def native_directory_snapshot_guidance(host_platform: HostPlatform) -> str:
    del host_platform
    return (
        "For a direct one-layer directory snapshot requested by the user, prefer list_dir with depth 1 "
        "over shell directory listings so the result stays structured and paginatable. "
        "Use exec_command only when the user explicitly asks for shell metadata such as permissions, "
        "owners, sizes, or timestamps. "
    )
