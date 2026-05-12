from __future__ import annotations

from dataclasses import dataclass

DEFAULT_GITHUB_REPO = "openai/codex"
DEFAULT_RUNTIME_VERSION = "current"
GITHUB_API_ROOT = "https://api.github.com/repos"
USER_AGENT = "AgentHub codex-sidecar-runtime-preparer"
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 300.0
DEFAULT_DOWNLOAD_RETRIES = 3


@dataclass(frozen=True, slots=True)
class PlatformSpec:
    platform_key: str
    target_triple: str
    npm_platform: str
    app_server_binary: str
    rg_binary: str
    bwrap_binary: str = ""

    @property
    def is_linux(self) -> bool:
        return self.platform_key.startswith("linux-")

    @property
    def is_windows(self) -> bool:
        return self.platform_key.startswith("windows-")


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    name: str
    url: str
    size: int = 0
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class SelectedAssets:
    app_server: ReleaseAsset
    npm_platform: ReleaseAsset
    bwrap: ReleaseAsset | None


PLATFORM_SPECS: dict[str, PlatformSpec] = {
    "linux-x86_64": PlatformSpec(
        platform_key="linux-x86_64",
        target_triple="x86_64-unknown-linux-musl",
        npm_platform="linux-x64",
        app_server_binary="codex-app-server",
        rg_binary="rg",
        bwrap_binary="bwrap",
    ),
    "linux-aarch64": PlatformSpec(
        platform_key="linux-aarch64",
        target_triple="aarch64-unknown-linux-musl",
        npm_platform="linux-arm64",
        app_server_binary="codex-app-server",
        rg_binary="rg",
        bwrap_binary="bwrap",
    ),
    "macos-arm64": PlatformSpec(
        platform_key="macos-arm64",
        target_triple="aarch64-apple-darwin",
        npm_platform="darwin-arm64",
        app_server_binary="codex-app-server",
        rg_binary="rg",
    ),
    "macos-x86_64": PlatformSpec(
        platform_key="macos-x86_64",
        target_triple="x86_64-apple-darwin",
        npm_platform="darwin-x64",
        app_server_binary="codex-app-server",
        rg_binary="rg",
    ),
    "windows-x86_64": PlatformSpec(
        platform_key="windows-x86_64",
        target_triple="x86_64-pc-windows-msvc",
        npm_platform="win32-x64",
        app_server_binary="codex-app-server.exe",
        rg_binary="rg.exe",
    ),
    "windows-aarch64": PlatformSpec(
        platform_key="windows-aarch64",
        target_triple="aarch64-pc-windows-msvc",
        npm_platform="win32-arm64",
        app_server_binary="codex-app-server.exe",
        rg_binary="rg.exe",
    ),
}
