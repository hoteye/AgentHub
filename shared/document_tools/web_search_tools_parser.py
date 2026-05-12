from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from shared.document_tools.web_search_tools_support import (
    _BLOCK_TAGS,
    _MAIN_CONTENT_TAGS,
    _clean_multiline,
    _clean_text,
)


class _HTMLPageExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._main_depth = 0
        self._title_parts: List[str] = []
        self._text_parts: List[str] = []
        self._main_text_parts: List[str] = []
        self._links: List[tuple[str, str, bool]] = []
        self._current_link_href: Optional[str] = None
        self._current_link_text: List[str] = []
        self._current_link_in_main = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        attr_map = {str(key): str(value or "") for key, value in attrs}
        if tag == "title":
            self._in_title = True
        if tag in _MAIN_CONTENT_TAGS or attr_map.get("role", "").lower() == "main":
            self._main_depth += 1
        if tag in _BLOCK_TAGS:
            self._text_parts.append("\n")
            if self._main_depth > 0:
                self._main_text_parts.append("\n")
        if tag == "a":
            href = ""
            for key, value in attrs:
                if key == "href":
                    href = str(value or "").strip()
                    break
            self._current_link_href = href or None
            self._current_link_text = []
            self._current_link_in_main = self._main_depth > 0

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag in _BLOCK_TAGS:
            self._text_parts.append("\n")
            if self._main_depth > 0:
                self._main_text_parts.append("\n")
        if tag in _MAIN_CONTENT_TAGS and self._main_depth > 0:
            self._main_depth -= 1
        if tag == "a":
            href = self._current_link_href
            text = _clean_text("".join(self._current_link_text))
            if href and text:
                self._links.append((href, text, self._current_link_in_main))
            self._current_link_href = None
            self._current_link_text = []
            self._current_link_in_main = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = str(data or "")
        if self._in_title:
            self._title_parts.append(text)
        self._text_parts.append(text)
        if self._main_depth > 0:
            self._main_text_parts.append(text)
        if self._current_link_href is not None:
            self._current_link_text.append(text)

    def extract(self) -> Dict[str, Any]:
        full_raw = _clean_multiline("".join(self._text_parts))
        main_raw = _clean_multiline("".join(self._main_text_parts))
        full_lines = [_clean_text(line) for line in full_raw.split("\n")]
        main_lines = [_clean_text(line) for line in main_raw.split("\n")]
        normalized_full_lines = [line for line in full_lines if line]
        normalized_main_lines = [line for line in main_lines if line]
        use_main = len(normalized_main_lines) >= 6 or len("\n".join(normalized_main_lines)) >= 300
        return {
            "title": _clean_text("".join(self._title_parts)),
            "text": "\n".join(normalized_main_lines if use_main else normalized_full_lines),
            "lines": normalized_main_lines if use_main else normalized_full_lines,
            "scope": "main" if use_main else "full",
            "links": self._links,
        }
