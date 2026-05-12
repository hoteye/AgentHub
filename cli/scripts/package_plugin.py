from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_plugin_root() -> Path:
    return _repo_root() / "plugins"


def _iter_files(plugin_dir: Path):
    for path in sorted(plugin_dir.rglob("*")):
        if not path.is_file():
            continue
        parts = path.parts
        if "__pycache__" in parts or ".pytest_cache" in parts:
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        yield path


def build_plugin_zip(*, plugin_name: str, plugin_root: Path, output_path: Path) -> Path:
    source_dir = (plugin_root / plugin_name).resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"plugin directory not found: {source_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _iter_files(source_dir):
            archive.write(path, arcname=str(path.relative_to(plugin_root)))
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Package one AgentHub plugin directory into a zip file.")
    parser.add_argument("--plugin", required=True, help="Plugin directory name under the plugin root.")
    parser.add_argument(
        "--plugin-root",
        default=str(_default_plugin_root()),
        help="Plugin root directory. Defaults to <repo>/plugins.",
    )
    parser.add_argument(
        "--output",
        help="Zip output path. Defaults to <repo>/artifacts/plugins/<plugin>.zip.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plugin_name = str(args.plugin or "").strip()
    if not plugin_name:
        raise SystemExit("--plugin is required")
    plugin_root = Path(str(args.plugin_root or "").strip()).resolve()
    output_path = (
        Path(str(args.output).strip()).resolve()
        if str(args.output or "").strip()
        else (_repo_root() / "artifacts" / "plugins" / f"{plugin_name}.zip").resolve()
    )
    packaged = build_plugin_zip(plugin_name=plugin_name, plugin_root=plugin_root, output_path=output_path)
    print(str(packaged))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
