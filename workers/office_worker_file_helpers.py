"""File extraction and conversion helpers for the Office worker."""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _extract_zip_safe(path: Path, extract_root: Path) -> List[Path]:
    output_dir = _unique_output_dir(extract_root, path.stem)
    extracted: List[Path] = []
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


def _find_7z_executable() -> Optional[str]:
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


def _extract_7z_safe(path: Path, extract_root: Path) -> List[Path]:
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
            f"7z extract failed: {path.name}; stdout={result.stdout.strip()}; stderr={result.stderr.strip()}"
        )
    extracted = [item for item in output_dir.rglob("*") if item.is_file()]
    return extracted


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
            f"LibreOffice convert failed: {path.name}; stdout={result.stdout.strip()}; stderr={result.stderr.strip()}"
        )
    converted = outdir / f"{path.stem}{target_ext}"
    if converted.exists():
        return converted
    generated = sorted(outdir.glob(f"*{target_ext}"))
    if len(generated) == 1:
        return generated[0]
    raise FileNotFoundError(f"converted output missing for {path.name}")


def _convert_legacy_office(path: Path, convert_root: Path) -> Path:
    suffix = path.suffix.lower()
    outdir = _unique_output_dir(convert_root, path.stem)
    if suffix == ".doc":
        return _run_soffice_convert(path, outdir, ".docx")
    return path


def _flatten_parseable_files(
    paths: List[Path],
    *,
    extract_root: Path,
    convert_root: Path,
    errors: List[Dict[str, Any]],
) -> List[Path]:
    resolved: List[Path] = []
    for path in paths:
        suffix = path.suffix.lower()
        if suffix == ".zip":
            try:
                extracted = _extract_zip_safe(path, extract_root)
            except Exception as exc:
                errors.append({"path": str(path), "stage": "extract", "error": str(exc)})
                continue
            resolved.extend(
                _flatten_parseable_files(
                    extracted,
                    extract_root=extract_root,
                    convert_root=convert_root,
                    errors=errors,
                )
            )
            continue
        if suffix == ".7z":
            try:
                extracted = _extract_7z_safe(path, extract_root)
            except Exception as exc:
                errors.append({"path": str(path), "stage": "extract", "error": str(exc)})
                continue
            resolved.extend(
                _flatten_parseable_files(
                    extracted,
                    extract_root=extract_root,
                    convert_root=convert_root,
                    errors=errors,
                )
            )
            continue
        if suffix in {".doc", ".xls"}:
            try:
                resolved.append(_convert_legacy_office(path, convert_root))
            except Exception as exc:
                errors.append({"path": str(path), "stage": "convert", "error": str(exc)})
            continue
        if suffix in {".docx", ".xlsx"}:
            resolved.append(path)
    return resolved
