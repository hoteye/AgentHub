from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_AGENTHUB_TIMELINE = Path("/tmp/live_agenthub_request_capture_20260414/timeline.jsonl")
DEFAULT_CODEX_TIMELINE = Path("/tmp/weather_field_diff_capture_20260414/timeline.jsonl")
DEFAULT_PROXY_LOG = Path("/tmp/live_header_proxy_20260414/proxy.log.jsonl")
DEFAULT_OUT_DIR = Path("/tmp/weather_header_tool_axes_20260414")
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

DROP_REQUEST_HEADERS = {
    "authorization",
    "host",
    "content-length",
    "connection",
    "accept-encoding",
}

WEATHER_DETAIL_MARKERS = (
    "°C",
    "℃",
    "最高",
    "最低",
    "气温",
    "多云",
    "晴",
    "降雨",
    "风力",
    "紫外线",
    "日出",
    "日落",
    "外套",
)


@dataclass(frozen=True)
class ReplayCase:
    body_family: str
    header_family: str
    tool_family: str

    @property
    def label(self) -> str:
        return f"{self.body_family}_body__{self.header_family}_headers__{self.tool_family}_tools"
