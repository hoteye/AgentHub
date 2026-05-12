from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import platform as py_platform
import shutil
import sys


@dataclass(frozen=True)
class HostPlatform:
    family: str
    os: str
    shell_kind: str
    shell_program: str
    list_dir_command: str
    print_working_dir_command: str
    python_version_command: str

    def normalize_shell_command(self, command: str) -> str:
        raw = str(command or "").strip()
        compact = " ".join(raw.split())
        if not compact:
            return ""
        lowered = compact.lower()
        if self.os == "windows":
            if lowered in {"ls", "dir"}:
                return "Get-ChildItem"
            if lowered in {"ls -a", "ls -la", "ls -al", "dir /a"}:
                return "Get-ChildItem -Force"
            if lowered in {"pwd", "cwd"}:
                return "Get-Location"
            return raw
        if lowered in {"dir", "get-childitem"}:
            return "ls"
        if lowered in {"dir /a", "ls -a", "ls -la", "ls -al", "get-childitem -force"}:
            return "ls -la"
        if lowered in {"get-location", "cwd"}:
            return "pwd"
        return raw

    def _ultimate_shell_program(self) -> str:
        return "cmd.exe" if self.os == "windows" else "/bin/sh"

    @staticmethod
    def _shell_name(shell: str | None) -> str | None:
        raw = str(shell or "").strip()
        if not raw:
            return None
        normalized = raw.replace("\\", "/").rstrip("/")
        base = normalized.rsplit("/", 1)[-1].lower()
        if base.endswith(".exe"):
            base = base[:-4]
        if base in {"bash", "zsh", "sh", "cmd", "pwsh", "powershell"}:
            return "powershell" if base == "pwsh" else base
        return None

    def _shell_candidates(self, shell_name: str) -> tuple[str, ...]:
        if shell_name == "bash":
            return ("bash", "/bin/bash")
        if shell_name == "zsh":
            return ("zsh", "/bin/zsh")
        if shell_name == "sh":
            return ("sh", "/bin/sh")
        if shell_name == "powershell":
            return (
                "pwsh.exe",
                "pwsh",
                "powershell.exe",
                "powershell",
                "/usr/local/bin/pwsh",
            )
        if shell_name == "cmd":
            return ("cmd.exe", "cmd")
        return ()

    def _default_user_shell_program(self, shell_name: str) -> str | None:
        env_name = "COMSPEC" if self.os == "windows" else "SHELL"
        raw = str(os.environ.get(env_name) or "").strip()
        if not raw:
            return None
        if self._shell_name(raw) != shell_name:
            return None
        candidate = Path(raw)
        if candidate.is_file():
            return str(candidate)
        return None

    def resolve_shell_program(self, shell: str | None = None) -> str:
        raw = str(shell or "").strip()
        if not raw:
            default_user_shell = self._default_runtime_shell_program()
            if default_user_shell:
                return default_user_shell
            return self.shell_program
        shell_name = self._shell_name(raw)
        if shell_name is None:
            return self._ultimate_shell_program()
        explicit_path = Path(raw)
        if explicit_path.is_file():
            return str(explicit_path)
        default_user_shell = self._default_user_shell_program(shell_name)
        if default_user_shell:
            return default_user_shell
        for candidate in self._shell_candidates(shell_name):
            found = shutil.which(candidate)
            if found:
                return found
            candidate_path = Path(candidate)
            if candidate_path.is_file():
                return str(candidate_path)
        return self._ultimate_shell_program()

    def _default_runtime_shell_program(self) -> str | None:
        env_name = "COMSPEC" if self.os == "windows" else "SHELL"
        shell_name = self._shell_name(os.environ.get(env_name))
        if shell_name is None:
            return None
        default_user_shell = self._default_user_shell_program(shell_name)
        if default_user_shell:
            return default_user_shell
        for candidate in self._shell_candidates(shell_name):
            found = shutil.which(candidate)
            if found:
                return found
            candidate_path = Path(candidate)
            if candidate_path.is_file():
                return str(candidate_path)
        return None

    def normalize_shell_override(self, shell: str | None = None) -> str | None:
        raw = str(shell or "").strip()
        if not raw:
            return None
        return self.resolve_shell_program(raw)

    def shell_command(self, command: str) -> str:
        normalized = self.normalize_shell_command(command)
        return f"/shell {normalized}" if normalized else ""

    def shell_exec_args(self, command: str) -> list[str]:
        normalized = self.normalize_shell_command(command)
        if self.os == "windows":
            return [
                self.resolve_shell_program(),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                normalized,
            ]
        return [self.resolve_shell_program(), "-lc", normalized]


def detect_host_platform(
    *,
    system_name: str | None = None,
    sys_platform: str | None = None,
) -> HostPlatform:
    system_name = str(system_name or py_platform.system() or "").strip().lower()
    sys_platform = str(sys_platform or sys.platform or "").strip().lower()
    if system_name == "windows" or sys_platform.startswith("win"):
        return HostPlatform(
            family="windows",
            os="windows",
            shell_kind="powershell",
            shell_program="powershell.exe",
            list_dir_command="Get-ChildItem -Force",
            print_working_dir_command="Get-Location",
            python_version_command="python -V",
        )
    if system_name == "darwin" or sys_platform == "darwin":
        return HostPlatform(
            family="unix",
            os="macos",
            shell_kind="posix",
            shell_program="/bin/sh",
            list_dir_command="ls -la",
            print_working_dir_command="pwd",
            python_version_command="python3 -V",
        )
    return HostPlatform(
        family="unix",
        os="linux",
        shell_kind="posix",
        shell_program="/bin/sh",
        list_dir_command="ls -la",
        print_working_dir_command="pwd",
        python_version_command="python3 -V",
    )


@lru_cache(maxsize=1)
def current_host_platform() -> HostPlatform:
    return detect_host_platform()
