#!/usr/bin/env python3
"""
Archive extraction and legacy office conversion helpers for document ingest.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from shared.document_tools.platform_paths import find_soffice_executable


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value).strip("_") or "file"


def _unique_output_dir(root: Path, seed: str) -> Path:
    base = root / _safe_name(seed)
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        return base
    index = 2
    while True:
        candidate = root / f"{_safe_name(seed)}_{index}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        index += 1


def extract_zip_safe(path: Path, extract_root: Path) -> list[Path]:
    output_dir = _unique_output_dir(extract_root, path.stem)
    extracted: list[Path] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_path = Path(info.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                continue
            target = output_dir / member_path
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as sink:
                sink.write(source.read())
            extracted.append(target)
    return extracted


def _find_7z_executable() -> str | None:
    for name in ("7z", "7z.exe", "7za", "7za.exe"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    candidates = [
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def extract_7z_safe(path: Path, extract_root: Path) -> list[Path]:
    seven_zip = _find_7z_executable()
    if not seven_zip:
        raise RuntimeError("7z executable not found")
    output_dir = _unique_output_dir(extract_root, path.stem)
    result = subprocess.run(
        [
            seven_zip,
            "x",
            str(path),
            f"-o{output_dir}",
            "-y",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"7z 解压失败: {path.name}; stdout={result.stdout.strip()}; stderr={result.stderr.strip()}"
        )
    return [item for item in output_dir.rglob("*") if item.is_file()]


def _run_soffice_convert(path: Path, outdir: Path, target_ext: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    soffice = find_soffice_executable()
    if not soffice:
        raise RuntimeError("LibreOffice soffice executable not found")
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            target_ext.lstrip("."),
            "--outdir",
            str(outdir),
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice 转换失败: {path.name}; stdout={result.stdout.strip()}; stderr={result.stderr.strip()}"
        )
    converted = outdir / f"{path.stem}{target_ext}"
    if not converted.exists():
        generated = sorted(outdir.glob(f"*{target_ext}"))
        if len(generated) == 1:
            return generated[0]
        raise FileNotFoundError(
            f"转换输出不存在: {converted}; stdout={result.stdout.strip()}; stderr={result.stderr.strip()}"
        )
    return converted


def convert_legacy_office(path: Path, convert_root: Path) -> Path:
    suffix = path.suffix.lower()
    outdir = _unique_output_dir(convert_root, path.stem)
    if suffix == ".doc":
        return _run_soffice_convert(path, outdir, ".docx")
    return path
