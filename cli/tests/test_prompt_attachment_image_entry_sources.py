from __future__ import annotations

import base64
import re
from pathlib import Path

from cli.agent_cli.models import (
    PROMPT_ATTACHMENT_SOURCE_TOOL_LOCAL_IMAGE_READ,
    PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT,
    prompt_attachment_source_kind,
)
from cli.agent_cli.models_mapping_runtime import prompt_attachment_from_path_data
from cli.agent_cli.ui.attachments import extract_attachment_references


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_UNC_RE = re.compile(r"^\\\\[^\\]+\\[^\\]+")
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7YQ1wAAAAASUVORK5CYII="
)


def _write_png(path: Path) -> None:
    path.write_bytes(_PNG_1X1)


def test_prompt_attachment_from_path_data_tags_user_local_image_from_supported_suffix(tmp_path: Path) -> None:
    image_path = tmp_path / "diagram.png"
    _write_png(image_path)

    attachment = prompt_attachment_from_path_data(str(image_path), source="composer_file_reference")

    assert attachment["source"] == PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT
    assert prompt_attachment_source_kind(str(attachment["source"])) == "user_local_image_attachment"


def test_prompt_attachment_from_path_data_tags_tool_local_image_from_supported_suffix(tmp_path: Path) -> None:
    image_path = tmp_path / "tool-image.png"
    _write_png(image_path)

    attachment = prompt_attachment_from_path_data(str(image_path), source="tool:view_image")

    assert attachment["source"] == PROMPT_ATTACHMENT_SOURCE_TOOL_LOCAL_IMAGE_READ
    assert prompt_attachment_source_kind(str(attachment["source"])) == "tool_local_image_read"


def test_prompt_attachment_from_path_data_tags_supported_image_suffix_without_reading_bytes(tmp_path: Path) -> None:
    fake_image_path = tmp_path / "fake.png"
    fake_image_path.write_text("not-an-image", encoding="utf-8")

    attachment = prompt_attachment_from_path_data(str(fake_image_path), source="composer_file_reference")

    assert attachment["source"] == PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT
    assert prompt_attachment_source_kind(str(attachment["source"])) == "user_local_image_attachment"


def test_prompt_attachment_from_path_data_does_not_tag_directory_with_image_suffix(tmp_path: Path) -> None:
    fake_dir = tmp_path / "folder.png"
    fake_dir.mkdir()

    attachment = prompt_attachment_from_path_data(str(fake_dir), source="composer_file_reference")

    assert attachment["source"] == "composer_file_reference"
    assert prompt_attachment_source_kind(str(attachment["source"])) == "local_file_attachment"


def test_extract_attachment_references_produces_image_specific_source_for_valid_local_image(tmp_path: Path) -> None:
    image_path = tmp_path / "cat.png"
    text_path = tmp_path / "notes.txt"
    _write_png(image_path)
    text_path.write_text("hello", encoding="utf-8")
    raw = f'check @{image_path} and @{text_path}'

    normalized_text, attachments = extract_attachment_references(
        raw,
        windows_drive_re=_WINDOWS_DRIVE_RE,
        windows_unc_re=_WINDOWS_UNC_RE,
    )

    assert str(image_path) in normalized_text
    assert str(text_path) in normalized_text
    by_path = {item.path: item.source for item in attachments}
    assert by_path[str(image_path)] == PROMPT_ATTACHMENT_SOURCE_USER_LOCAL_IMAGE_ATTACHMENT
    assert by_path[str(text_path)] == "composer_file_reference"
