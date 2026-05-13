from __future__ import annotations

import os
import shutil
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from cli.agent_cli.startup_cwd import resolve_startup_cwd


def _argv_requests_help(argv: Sequence[str] | None) -> bool:
    return any(str(item or "").strip() in {"--help", "-h"} for item in list(argv or []))


def _has_mcp_serve_request(argv: Sequence[str] | None) -> bool:
    if argv is None:
        return False
    args = [str(item or "").strip() for item in list(argv)]
    return len(args) >= 2 and args[0] == "mcp" and args[1] == "serve"


def _configure_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            continue


def _git_install_hint() -> str:
    return "\n".join(
        [
            "AgentHub requires git, but git was not found in PATH.",
            "Install git and run AgentHub again.",
            "",
            "Ubuntu/Debian: sudo apt install git",
            "Fedora: sudo dnf install git",
            "Arch: sudo pacman -S git",
            "macOS: brew install git",
        ]
    )


def _ensure_git_dependency(*, stderr: TextIO | None = None) -> bool:
    if shutil.which("git"):
        return True
    print(_git_install_hint(), file=stderr or sys.stderr)
    return False


def _tmux_preview_supported_on_host() -> bool:
    return sys.platform != "win32"


def _tmux_install_hint() -> str:
    return "\n".join(
        [
            "AgentHub file/URL preview panes need tmux, but tmux was not found in PATH.",
            "Install tmux to enable the preview pane. Continuing without the preview pane.",
            "",
            "Ubuntu/Debian: sudo apt install tmux",
            "Fedora: sudo dnf install tmux",
            "Arch: sudo pacman -S tmux",
            "macOS: brew install tmux",
        ]
    )


def _warn_missing_tmux_dependency_for_tui(
    argv: Sequence[str],
    *,
    headless: bool,
    stderr: TextIO | None = None,
) -> None:
    if not bool(getattr(sys, "frozen", False)):
        return
    if _argv_requests_help(argv):
        return
    if not _tmux_preview_supported_on_host():
        return
    if str(shutil.which("tmux") or "").strip():
        return
    if str(os.environ.get("AGENTHUB_TMUX_DEPENDENCY_CHECKED") or "").strip():
        return
    if headless:
        return
    print(_tmux_install_hint(), file=stderr or sys.stderr)


def _ensure_import_paths() -> None:
    package_dir = Path(__file__).resolve().parent
    cli_root = str(package_dir.parent)
    repo_root_path = package_dir.parents[1]
    repo_root = str(repo_root_path)
    for candidate in (cli_root, repo_root):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    from cli.agent_cli.runtime_paths import ensure_runtime_project_root_env

    ensure_runtime_project_root_env()


def _configure_startup_debug(raw_argv: Sequence[str]) -> None:
    from cli.agent_cli.debug_cli import preconfigure_debug_from_argv
    from cli.agent_cli.startup_debug import (
        enable_startup_faulthandler,
        install_startup_exit_logging,
        startup_log,
    )

    preconfigure_debug_from_argv(raw_argv)
    enable_startup_faulthandler()
    install_startup_exit_logging()
    startup_log(f"main.enter argv={list(raw_argv)}")


def _startup_log(message: str) -> None:
    try:
        from cli.agent_cli.startup_debug import startup_log

        startup_log(message)
    except Exception:
        return


def _prepare_interactive_tui_terminal_signals() -> None:
    try:
        from cli.agent_cli.startup_debug import ignore_terminal_stop_signals, startup_log

        ignore_terminal_stop_signals()
        startup_log("terminal.stop_signals.ignored_for_tui_startup")
    except Exception:
        return


def _build_tui_runtime(args, runtime):
    from cli.agent_cli.resume_support import (
        apply_runtime_resume_request,
        has_explicit_resume_request,
    )
    from cli.agent_cli.runtime_factory import build_persistent_runtime
    from cli.agent_cli.runtime_policy import RuntimePolicy

    resume_thread_id = getattr(args, "resume", None)
    resume_rollout_path = getattr(args, "resume_path", None)
    resume_last = bool(getattr(args, "resume_last", False))
    startup_cwd = resolve_startup_cwd()
    explicit_resume = has_explicit_resume_request(
        thread_id=resume_thread_id,
        rollout_path=resume_rollout_path,
        resume_last=resume_last,
    )
    if runtime is None:
        runtime_policy = RuntimePolicy.normalized(
            permission_mode=getattr(args, "permission_mode", None),
            approval_policy=getattr(args, "approval_policy", None) or "never",
            sandbox_mode=getattr(args, "sandbox_mode", None),
            web_search_mode=getattr(args, "web_search_mode", None),
            network_access_enabled=getattr(args, "network_access", None),
        )
        tab_restore_prefetch = _start_tui_tab_restore_prefetch(
            runtime_policy=runtime_policy,
            startup_cwd=startup_cwd,
            explicit_resume=explicit_resume,
        )
        runtime = build_persistent_runtime(
            runtime_policy=runtime_policy,
            resume_active_thread=False,
            start_thread_if_unavailable=False,
            build_initial_planner=False,
        )
        if tab_restore_prefetch is not None:
            runtime._codex_sidecar_restore_prefetch = tab_restore_prefetch
        runtime.tui_tab_manifest_enabled = not explicit_resume
        if not explicit_resume:
            _start_new_tui_thread(runtime, startup_cwd)
    elif not explicit_resume:
        try:
            runtime.tui_tab_manifest_enabled = True
        except Exception:
            pass
    if explicit_resume:
        apply_runtime_resume_request(
            runtime,
            thread_id=resume_thread_id,
            rollout_path=resume_rollout_path,
            resume_last=resume_last,
        )
    _configure_tui_runtime_policy(runtime, args)
    return runtime


def _start_tui_tab_restore_prefetch(
    *,
    runtime_policy,
    startup_cwd: Path,
    explicit_resume: bool,
):
    if explicit_resume:
        return None
    try:
        from cli.agent_cli.ui.tab_session_restore_prefetch import (
            start_active_codex_sidecar_restore_prefetch,
        )

        return start_active_codex_sidecar_restore_prefetch(
            runtime_policy=runtime_policy,
            startup_cwd=startup_cwd,
        )
    except Exception:
        return None


def _start_new_tui_thread(runtime, startup_cwd) -> None:
    set_cwd = getattr(runtime, "set_cwd", None)
    if callable(set_cwd):
        set_cwd(startup_cwd)
    start_thread = getattr(runtime, "start_thread", None)
    if callable(start_thread):
        start_thread()


def _tui_exit_summary_text(app) -> str:
    mgr = getattr(app, "_tab_manager", None)
    if mgr is not None and getattr(mgr, "_tab_order", None):
        alphabet = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        lines = []
        for index, tab_id in enumerate(mgr._tab_order):
            session = mgr._tabs.get(tab_id)
            if session is None:
                continue
            tid = str(getattr(session, "thread_id", "") or "").strip()
            code = alphabet[index] if index < len(alphabet) else str(index + 1)
            if tid:
                lines.append(f"{code}: {tid}")
        if lines:
            return "Sessions:\n" + "\n".join(lines)
    thread_id = str(getattr(app, "_exit_thread_id", "") or "").strip()
    if thread_id:
        return f"resume {thread_id}"
    resume_command = str(getattr(app, "_exit_resume_command", "") or "").strip()
    if not resume_command:
        return ""
    parts = [part for part in resume_command.split() if part]
    if len(parts) >= 3 and parts[-2] == "resume":
        return f"resume {parts[-1]}"
    return resume_command


def _tui_should_print_exit_summary(app, args) -> bool:
    if not getattr(app, "_exit_requested", False):
        return False
    if not getattr(app, "_exit_summary_requires_post_run_print", False):
        return False
    resume_thread_id = str(getattr(args, "resume", "") or "").strip()
    resume_rollout_path = str(getattr(args, "resume_path", "") or "").strip()
    resume_last = bool(getattr(args, "resume_last", False))
    if resume_thread_id or resume_rollout_path or resume_last:
        return False
    return True


def _tui_mark_keyboard_interrupt_exit(app, runtime) -> None:
    populate_exit = getattr(app, "_populate_exit_request_from_runtime", None)
    if callable(populate_exit):
        try:
            populate_exit()
        except Exception:
            pass
    thread_id = str(getattr(app, "_exit_thread_id", "") or "").strip()
    resume_command = str(getattr(app, "_exit_resume_command", "") or "").strip()
    if not thread_id:
        thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
    if not resume_command and thread_id:
        resume_command = f"agenthub resume {thread_id}"
    if thread_id:
        app._exit_thread_id = thread_id
    if resume_command:
        app._exit_resume_command = resume_command
    if thread_id or resume_command:
        app._exit_requested = True
        app._exit_summary_requires_post_run_print = True
    begin_shutdown = getattr(app, "_begin_shutdown", None)
    if callable(begin_shutdown):
        try:
            begin_shutdown()
        except Exception:
            pass


def _configure_tui_runtime_policy(runtime, args) -> None:
    configure = getattr(runtime, "configure_runtime_policy", None)
    if not callable(configure):
        return
    approval_policy = getattr(args, "approval_policy", None)
    sandbox_mode = getattr(args, "sandbox_mode", None)
    network_access_enabled = getattr(args, "network_access", None)
    permission_mode = getattr(args, "permission_mode", None)
    if str(permission_mode or "").strip():
        from cli.agent_cli.runtime_permission_mode import resolve_permission_mode_updates

        current_policy = getattr(runtime, "runtime_policy", None)
        resolution = resolve_permission_mode_updates(
            current_approval_policy=getattr(current_policy, "approval_policy", None),
            current_sandbox_mode=getattr(current_policy, "sandbox_mode", None),
            current_network_access_enabled=getattr(current_policy, "network_access_enabled", None),
            permission_mode=permission_mode,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            network_access_enabled=network_access_enabled,
        )
        approval_policy = resolution.approval_policy
        sandbox_mode = resolution.sandbox_mode
        network_access_enabled = resolution.network_access_enabled
    configure(
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=getattr(args, "web_search_mode", None),
        network_access_enabled=network_access_enabled,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime=None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    raw_argv = list(argv) if argv is not None else list(sys.argv[1:])
    try:
        _configure_startup_debug(raw_argv)
        _configure_stdio()
        _startup_log("stdio.configured")
        _ensure_import_paths()
        _startup_log("import_paths.ready")
        if not _argv_requests_help(raw_argv) and not _ensure_git_dependency(stderr=stderr):
            _startup_log("dependency.git.missing")
            return 1

        from cli.agent_cli.debug_cli import configure_debug_from_args

        if _has_mcp_serve_request(raw_argv):
            _startup_log("mcp.serve.begin")
            from cli.agent_cli.mcp.serve import main as mcp_serve_main

            return mcp_serve_main(
                raw_argv[1:],
                runtime=runtime,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
            )

        from cli.agent_cli.subcommands import dispatch_subcommand

        _startup_log("subcommand.dispatch.begin")
        subcommand_exit_code = dispatch_subcommand(
            raw_argv,
            runtime=runtime,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
        if subcommand_exit_code is not None:
            _startup_log(f"subcommand.dispatch.end status={subcommand_exit_code}")
            return subcommand_exit_code

        _startup_log("headless.import.begin")
        from cli.agent_cli.headless import build_parser, has_headless_request, run_headless
        from cli.agent_cli.resume_support import normalize_resume_cli_args

        _startup_log("headless.import.end")

        try:
            _startup_log("argv.normalize.begin")
            normalized_argv = normalize_resume_cli_args(raw_argv)
            _startup_log(f"argv.normalize.end argv={normalized_argv}")
        except ValueError as exc:
            _startup_log(f"argv.normalize.error error={exc}")
            print(f"cli error: {exc}", file=stderr or sys.stderr)
            return 1

        _startup_log("argparse.begin")
        args = build_parser().parse_args(normalized_argv)
        configure_debug_from_args(args)
        headless_request = has_headless_request(args)
        _startup_log(
            "argparse.end "
            f"headless={headless_request} "
            f"serve={getattr(args, 'serve', None)} "
            f"prompt={bool(getattr(args, 'prompt', None))} "
            f"sandbox={getattr(args, 'sandbox_mode', None)} "
            f"approval={getattr(args, 'approval_policy', None)}"
        )
        if headless_request:
            _startup_log("headless.run.begin")
            result = run_headless(
                args,
                runtime=runtime,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
            )
            _startup_log(f"headless.run.end status={result}")
            return result

        _warn_missing_tmux_dependency_for_tui(
            normalized_argv,
            headless=headless_request,
            stderr=stderr,
        )
        _prepare_interactive_tui_terminal_signals()

        try:
            _startup_log("tui.app_import.begin")
            from cli.agent_cli.app import AgentCliApp

            _startup_log("tui.app_import.end")
        except ModuleNotFoundError as exc:
            missing = getattr(exc, "name", "unknown")
            _startup_log(f"tui.app_import.module_not_found missing={missing}")
            if missing in {"textual", "rich"}:
                message = (
                    "Missing TUI dependencies.\n"
                    "Install them with:\n"
                    "python -m pip install -r requirements.txt"
                )
                print(message, file=stderr or sys.stderr)
                return 1
            raise

        try:
            _startup_log("tui.runtime.begin")
            tui_runtime = _build_tui_runtime(args, runtime)
            _startup_log("tui.runtime.end")
        except Exception as exc:
            _startup_log(f"tui.runtime.error error={exc!r}")
            _startup_log(traceback.format_exc().rstrip())
            print(f"tui error: {exc}", file=stderr or sys.stderr)
            return 1

        _startup_log("tui.app.init.begin")
        app = AgentCliApp(
            runtime=tui_runtime,
            language=getattr(args, "lang", None),
            theme_id=getattr(args, "theme", None),
        )
        _startup_log("tui.app.init.end")
        _startup_log("tui.run.begin")
        try:
            app.run()
        except KeyboardInterrupt:
            _startup_log("tui.run.keyboard_interrupt")
            _tui_mark_keyboard_interrupt_exit(app, tui_runtime)
            if _tui_should_print_exit_summary(app, args):
                exit_summary = _tui_exit_summary_text(app)
                if exit_summary:
                    print(exit_summary, file=stdout or sys.stdout)
            return 130
        _startup_log("tui.run.end")
        if _tui_should_print_exit_summary(app, args):
            exit_summary = _tui_exit_summary_text(app)
            if exit_summary:
                print(exit_summary, file=stdout or sys.stdout)
        return 0
    except BaseException as exc:
        _startup_log(f"main.fatal {exc.__class__.__name__}: {exc}")
        _startup_log(traceback.format_exc().rstrip())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
