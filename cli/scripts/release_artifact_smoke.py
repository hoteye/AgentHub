#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SMOKE_COMMAND_TIMEOUT_SECONDS = 120.0
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_release  # noqa: E402


def artifact_root() -> Path:
    releases_dir = ROOT / "cli" / "artifacts" / "releases"
    version = build_release.cli_version()
    platform_tag = build_release.detect_platform_tag()
    target = releases_dir / f"agenthub-cli-{version}-{platform_tag}"
    if not target.exists():
        raise FileNotFoundError(f"missing packaged release directory: {target}")
    return target


def executable_path(bundle_root: Path) -> Path:
    candidates = [bundle_root / "agenthub-cli.exe", bundle_root / "agenthub-cli"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"missing release executable under: {bundle_root}")


def _needs_windows_local_stage(bundle_root: Path) -> bool:
    return os.name == "nt" and str(bundle_root).startswith("\\\\")


@contextmanager
def smoke_bundle_root(bundle_root: Path):
    if not _needs_windows_local_stage(bundle_root):
        yield bundle_root
        return

    temp_root = Path(tempfile.mkdtemp(prefix=f"{bundle_root.name}-smoke-"))
    staged_root = temp_root / bundle_root.name
    try:
        shutil.copytree(bundle_root, staged_root)
        yield staged_root
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_smoke_command(executable: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    try:
        result = subprocess.run(
            [str(executable), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=SMOKE_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        raise RuntimeError(
            f"smoke command timed out after {SMOKE_COMMAND_TIMEOUT_SECONDS:g}s: "
            f"{executable} {' '.join(args)}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        ) from exc
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0:
        raise RuntimeError(
            f"smoke command failed ({result.returncode}): {executable} {' '.join(args)}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        )
    combined = f"{stdout}\n{stderr}".strip()
    if "No such file or directory" in combined:
        raise RuntimeError(
            f"smoke command surfaced missing runtime asset: {executable} {' '.join(args)}\noutput:\n{combined}"
        )
    if "Traceback (most recent call last)" in combined:
        raise RuntimeError(
            f"smoke command crashed: {executable} {' '.join(args)}\noutput:\n{combined}"
        )
    return result


def require_output(result: subprocess.CompletedProcess[str], *tokens: str) -> None:
    text = result.stdout or ""
    normalized_text = " ".join(text.split())
    for token in tokens:
        normalized_token = " ".join(str(token or "").split())
        if token not in text and normalized_token not in normalized_text:
            raise RuntimeError(f"expected token {token!r} in smoke output:\n{text}")


def main(argv: list[str] | None = None) -> int:
    del argv
    bundle_root = artifact_root()

    with smoke_bundle_root(bundle_root) as smoke_root:
        executable = executable_path(smoke_root)

        help_result = run_smoke_command(executable, "--help")
        require_output(
            help_result,
            "Reference-like CLI for AgentHub local automation and provider-backed workflows.",
        )

        version_result = run_smoke_command(executable, "--version")
        require_output(version_result, f"agenthub-cli {build_release.cli_version()}")

        provider_result = run_smoke_command(executable, "--provider-status")
        require_output(
            provider_result,
            "provider status",
            "provider_name=openai",
            "provider_model=gpt-5.5",
            "model_key=gpt_55",
            "provider_base_url=https://codexcs.ysaikeji.cn/v1",
            "provider_ready=",
        )

        headless_provider_result = run_smoke_command(
            executable, "--headless", "--prompt", "/provider verbose"
        )
        require_output(
            headless_provider_result,
            "provider status",
            "provider_name=openai",
            "provider_model=gpt-5.5",
            "model_key=gpt_55",
            "provider_ready=",
        )

    print(f"release smoke ok: {bundle_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
