from __future__ import annotations

from cli.agent_cli.media_content_runtime import (
    image_content_items_from_output,
    input_image_item_from_image_block,
    normalized_input_image_item,
)


def test_normalized_input_image_item_preserves_image_url_and_detail() -> None:
    item = normalized_input_image_item(
        {
            "image_url": "data:image/png;base64,AAA",
            "detail": "high",
        }
    )

    assert item == {
        "type": "input_image",
        "image_url": "data:image/png;base64,AAA",
        "detail": "high",
    }


def test_image_content_items_from_output_extracts_nested_content_shape() -> None:
    items = image_content_items_from_output(
        {
            "structured_content": {
                "content": [
                    {"type": "text", "text": "preview"},
                    {"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": "low"},
                ]
            }
        }
    )

    assert items == [
        {"type": "input_text", "text": "preview"},
        {"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": "low"},
    ]


def test_image_content_items_from_output_extracts_media_ingest_result_contract() -> None:
    items = image_content_items_from_output(
        {
            "ok": True,
            "image_artifacts": [
                {
                    "path": "/tmp/sample.png",
                    "mime_type": "image/png",
                    "size_bytes": 42,
                    "width": 10,
                    "height": 12,
                    "image_url": "data:image/png;base64,AAA",
                    "detail": "high",
                }
            ],
        }
    )

    assert items == [
        {
            "type": "input_image",
            "image_url": "data:image/png;base64,AAA",
            "detail": "high",
        }
    ]


def test_input_image_item_from_image_block_preserves_original_detail() -> None:
    item = input_image_item_from_image_block(
        {
            "type": "image",
            "detail": "original",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "AAA",
            },
        }
    )

    assert item == {
        "type": "input_image",
        "image_url": "data:image/png;base64,AAA",
        "detail": "original",
    }


def test_input_image_item_from_image_block_fails_closed_for_non_image_payload() -> None:
    item = input_image_item_from_image_block(
        {
            "type": "image",
            "detail": "original",
            "source": {
                "type": "base64",
                "media_type": "text/plain",
                "data": "AAA",
            },
        }
    )

    assert item is None
