from __future__ import annotations

import math
import struct
import zlib


def _clamp(value: float, *, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", checksum)


def _rgba_png_bytes(*, size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    raw_rows = bytearray()
    for row_index in range(size):
        raw_rows.append(0)
        row_start = row_index * size
        for red, green, blue, alpha in pixels[row_start : row_start + size]:
            raw_rows.extend((red, green, blue, alpha))
    png_header = b"\x89PNG\r\n\x1a\n"
    image_header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"".join(
        (
            png_header,
            _png_chunk(b"IHDR", image_header),
            _png_chunk(b"IDAT", zlib.compress(bytes(raw_rows), 9)),
            _png_chunk(b"IEND", b""),
        )
    )


def _blend_color(
    base: tuple[int, int, int, int],
    overlay: tuple[int, int, int],
    alpha: float,
) -> tuple[int, int, int, int]:
    overlay_alpha = _clamp(alpha)
    base_alpha = base[3] / 255.0
    result_alpha = overlay_alpha + base_alpha * (1.0 - overlay_alpha)
    if result_alpha <= 0:
        return (0, 0, 0, 0)
    channels = []
    for channel_index, overlay_channel in enumerate(overlay):
        base_channel = base[channel_index]
        value = (
            overlay_channel * overlay_alpha + base_channel * base_alpha * (1.0 - overlay_alpha)
        ) / result_alpha
        channels.append(int(round(value)))
    return (channels[0], channels[1], channels[2], int(round(result_alpha * 255)))


def _rounded_square_alpha(normalized_x: float, normalized_y: float, *, size: int) -> float:
    half_width = 0.45
    radius = 0.18
    distance_x = abs(normalized_x - 0.5) - half_width + radius
    distance_y = abs(normalized_y - 0.5) - half_width + radius
    outside_x = max(distance_x, 0.0)
    outside_y = max(distance_y, 0.0)
    signed_distance = math.hypot(outside_x, outside_y) - radius
    return _clamp(0.5 - signed_distance * size)


def _distance_to_segment(
    point_x: float,
    point_y: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    start_x, start_y = start
    end_x, end_y = end
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared <= 0:
        return math.hypot(point_x - start_x, point_y - start_y)
    projection = _clamp(
        ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y) / length_squared
    )
    nearest_x = start_x + projection * delta_x
    nearest_y = start_y + projection * delta_y
    return math.hypot(point_x - nearest_x, point_y - nearest_y)


def _shape_alpha(distance: float, radius: float, *, size: int) -> float:
    return _clamp((radius - distance) * size * 1.8)


def _agenthub_icon_pixels(size: int) -> list[tuple[int, int, int, int]]:
    pixels: list[tuple[int, int, int, int]] = []
    center = (0.5, 0.5)
    nodes = (
        (0.50, 0.18),
        (0.77, 0.34),
        (0.77, 0.66),
        (0.50, 0.82),
        (0.23, 0.66),
        (0.23, 0.34),
    )
    edges = tuple((nodes[index], nodes[(index + 1) % len(nodes)]) for index in range(len(nodes)))
    spokes = tuple((center, node) for node in nodes)
    for row_index in range(size):
        normalized_y = (row_index + 0.5) / size
        for column_index in range(size):
            normalized_x = (column_index + 0.5) / size
            background_alpha = _rounded_square_alpha(normalized_x, normalized_y, size=size)
            gradient = _clamp((normalized_x + normalized_y) / 2.0)
            background = (
                int(round(9 + 16 * gradient)),
                int(round(16 + 53 * gradient)),
                int(round(36 + 86 * gradient)),
            )
            pixel = _blend_color((0, 0, 0, 0), background, background_alpha)

            for start, end in edges:
                distance = _distance_to_segment(normalized_x, normalized_y, start, end)
                pixel = _blend_color(
                    pixel,
                    (73, 222, 255),
                    _shape_alpha(distance, 0.018, size=size) * background_alpha * 0.55,
                )
            for start, end in spokes:
                distance = _distance_to_segment(normalized_x, normalized_y, start, end)
                pixel = _blend_color(
                    pixel,
                    (112, 255, 222),
                    _shape_alpha(distance, 0.024, size=size) * background_alpha * 0.75,
                )

            center_distance = math.hypot(normalized_x - center[0], normalized_y - center[1])
            pixel = _blend_color(
                pixel,
                (11, 24, 50),
                _shape_alpha(center_distance, 0.125, size=size) * background_alpha,
            )
            pixel = _blend_color(
                pixel,
                (148, 255, 232),
                _shape_alpha(abs(center_distance - 0.092), 0.014, size=size) * background_alpha,
            )
            for node_x, node_y in nodes:
                node_distance = math.hypot(normalized_x - node_x, normalized_y - node_y)
                pixel = _blend_color(
                    pixel,
                    (198, 255, 244),
                    _shape_alpha(node_distance, 0.052, size=size) * background_alpha,
                )
                pixel = _blend_color(
                    pixel,
                    (56, 205, 255),
                    _shape_alpha(node_distance, 0.030, size=size) * background_alpha,
                )
            pixels.append(pixel)
    return pixels


def _agenthub_icon_png(size: int) -> bytes:
    return _rgba_png_bytes(size=size, pixels=_agenthub_icon_pixels(size))


def _ico_and_mask_bytes(*, size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    row_stride = ((size + 31) // 32) * 4
    mask = bytearray(row_stride * size)
    for row_index in range(size):
        source_row = size - 1 - row_index
        for column_index in range(size):
            alpha = pixels[source_row * size + column_index][3]
            if alpha >= 128:
                continue
            byte_index = row_index * row_stride + column_index // 8
            mask[byte_index] |= 0x80 >> (column_index % 8)
    return bytes(mask)


def _ico_dib_bytes(*, size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    xor_bitmap = bytearray()
    for row_index in range(size - 1, -1, -1):
        row_start = row_index * size
        for red, green, blue, alpha in pixels[row_start : row_start + size]:
            xor_bitmap.extend((blue, green, red, alpha))
    and_mask = _ico_and_mask_bytes(size=size, pixels=pixels)
    image_size = len(xor_bitmap) + len(and_mask)
    bitmap_info_header = struct.pack(
        "<IiiHHIIiiII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        image_size,
        0,
        0,
        0,
        0,
    )
    return bitmap_info_header + bytes(xor_bitmap) + and_mask


def _agenthub_icon_dib(size: int) -> bytes:
    return _ico_dib_bytes(size=size, pixels=_agenthub_icon_pixels(size))


def build_agenthub_windows_icon_bytes() -> bytes:
    icon_sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [(size, _agenthub_icon_dib(size)) for size in icon_sizes]
    offset = 6 + 16 * len(images)
    directory_entries = []
    image_payloads = []
    for size, payload in images:
        width_byte = 0 if size >= 256 else size
        directory_entries.append(
            struct.pack("<BBBBHHII", width_byte, width_byte, 0, 0, 1, 32, len(payload), offset)
        )
        image_payloads.append(payload)
        offset += len(payload)
    return (
        struct.pack("<HHH", 0, 1, len(images))
        + b"".join(directory_entries)
        + b"".join(image_payloads)
    )
