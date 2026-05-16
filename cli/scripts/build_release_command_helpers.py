from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path


def pyinstaller_command(
    *,
    bundle_name: str,
    mode: str,
    dist_dir: Path,
    build_dir: Path,
    spec_dir: Path,
    repo_root_func: Callable[[], Path],
    cli_root_func: Callable[[], Path],
    platform_system_func: Callable[[], str],
    agenthub_windows_icon_path_func: Callable[[Path], Path],
    runtime_data_mappings_func: Callable[..., list[tuple[Path, str]]],
    add_data_arg_func: Callable[[list[str], Path, str], None],
    add_collect_func: Callable[[list[str], str], None],
    maybe_add_collect_func: Callable[[list[str], str], None],
    add_hidden_import_func: Callable[[list[str], str], None],
    maybe_add_hidden_import_func: Callable[[list[str], str], None],
    pyinstaller_optional_heavy_excludes: tuple[str, ...],
    canonical_cli_dynamic_hidden_imports: tuple[str, ...],
) -> list[str]:
    root = repo_root_func()
    cli = cli_root_func()
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--console",
        "--name",
        bundle_name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(root),
        "--paths",
        str(cli),
    ]
    if platform_system_func().lower() == "windows":
        command.extend(["--icon", str(agenthub_windows_icon_path_func(spec_dir))])
    command.append("--onedir" if mode == "onedir" else "--onefile")
    for module_name in pyinstaller_optional_heavy_excludes:
        command.extend(["--exclude-module", module_name])
    for source, dest in runtime_data_mappings_func(root=root, cli=cli):
        add_data_arg_func(command, source, dest)
    add_collect_func(command, "cli.agent_cli")
    for module_name in canonical_cli_dynamic_hidden_imports:
        add_hidden_import_func(command, module_name)
    for package_name in (
        "textual",
        "rich",
        "openai",
        "agent_cli",
        "gateway",
        "workers",
    ):
        maybe_add_collect_func(command, package_name)
    for hidden in (
        "tools.office_tools",
        "tools.internal_policy_tools",
        "tools.web_search_tools",
        "workers.actions.worker",
    ):
        maybe_add_hidden_import_func(command, hidden)
    command.append(str(cli / "agent_cli" / "__main__.py"))
    return command
