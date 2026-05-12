from __future__ import annotations

import bisect
import ctypes
import ctypes.util
import os
import re
from functools import lru_cache


_UBRK_WORD = 1


class _IcuWordBreaker:
    def __init__(self, library_path: str) -> None:
        lib = ctypes.CDLL(library_path)
        suffix = _resolve_icu_symbol_suffix(lib, library_path)
        if suffix is None:
            raise RuntimeError(f"Could not resolve ICU word break symbols from {library_path}")

        self._open = getattr(lib, f"ubrk_open_{suffix}")
        self._open.argtypes = [
            ctypes.c_int32,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
        ]
        self._open.restype = ctypes.c_void_p

        self._set_text = getattr(lib, f"ubrk_setText_{suffix}")
        self._set_text.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint16),
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
        ]
        self._set_text.restype = None

        self._preceding = getattr(lib, f"ubrk_preceding_{suffix}")
        self._preceding.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        self._preceding.restype = ctypes.c_int32

        self._following = getattr(lib, f"ubrk_following_{suffix}")
        self._following.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        self._following.restype = ctypes.c_int32

        self._close = getattr(lib, f"ubrk_close_{suffix}")
        self._close.argtypes = [ctypes.c_void_p]
        self._close.restype = None

    def word_range_at(self, text: str, index: int) -> tuple[int, int] | None:
        if not text or not (0 <= index < len(text)):
            return None

        utf16_offsets = _utf16_offsets(text)
        data = text.encode("utf-16-le")
        buffer = (ctypes.c_uint16 * (len(data) // 2)).from_buffer_copy(data)

        error = ctypes.c_int32(0)
        iterator = self._open(_UBRK_WORD, None, buffer, len(buffer), ctypes.byref(error))
        if not iterator or error.value > 0:
            return None

        try:
            error = ctypes.c_int32(0)
            self._set_text(iterator, buffer, len(buffer), ctypes.byref(error))
            if error.value > 0:
                return None

            char_start = utf16_offsets[index]
            char_end = utf16_offsets[index + 1]
            start_u16 = int(self._preceding(iterator, char_end))
            end_u16 = int(self._following(iterator, char_start))
            if start_u16 < 0 or end_u16 < 0 or end_u16 < start_u16:
                return None

            start = _utf16_offset_to_codepoint_index(utf16_offsets, start_u16)
            end = _utf16_offset_to_codepoint_index(utf16_offsets, end_u16)
            if not (0 <= start <= index < end <= len(text)):
                return None
            return start, end
        finally:
            self._close(iterator)


def word_range_at(text: str, index: int) -> tuple[int, int] | None:
    breaker = _load_icu_word_breaker()
    if breaker is None:
        return None
    try:
        return breaker.word_range_at(text, index)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_icu_word_breaker() -> _IcuWordBreaker | None:
    candidates = _icu_library_candidates()
    for candidate in candidates:
        try:
            return _IcuWordBreaker(candidate)
        except Exception:
            continue
    return None


def _icu_library_candidates() -> tuple[str, ...]:
    candidates: list[str] = []
    for probe in (
        ctypes.util.find_library("icuuc"),
        "/opt/miniconda3/lib/libicuuc.so.73",
        "/usr/lib/x86_64-linux-gnu/libicuuc.so",
        "/usr/local/lib/libicuuc.so",
    ):
        if not probe:
            continue
        if probe not in candidates:
            candidates.append(probe)
    return tuple(candidates)


def _resolve_icu_symbol_suffix(lib: ctypes.CDLL, library_path: str) -> str | None:
    guessed_versions: list[str] = []
    for path in {library_path, os.path.realpath(library_path)}:
        guessed_versions.extend(re.findall(r"\.so\.(\d+)", path))
    for version in guessed_versions:
        try:
            getattr(lib, f"ubrk_open_{version}")
            return version
        except AttributeError:
            continue
    for version in range(99, 40, -1):
        try:
            getattr(lib, f"ubrk_open_{version}")
            return str(version)
        except AttributeError:
            continue
    return None


def _utf16_offsets(text: str) -> list[int]:
    offsets = [0]
    total = 0
    for char in text:
        total += len(char.encode("utf-16-le")) // 2
        offsets.append(total)
    return offsets


def _utf16_offset_to_codepoint_index(offsets: list[int], target: int) -> int:
    index = bisect.bisect_left(offsets, target)
    if index < len(offsets) and offsets[index] == target:
        return index
    return max(0, min(len(offsets) - 1, bisect.bisect_right(offsets, target) - 1))
