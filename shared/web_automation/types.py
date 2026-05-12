from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class BrowserProfileSpec:
    name: str
    color: str
    driver: str = "openclaw"
    default: bool = False
    attach_only: bool = False
    executable_path: str = ""
    user_data_dir: str = ""
    cdp_url: str = ""
    headless: Optional[bool] = None


@dataclass
class BrowserPageRef:
    ref: str
    role: str
    name: Optional[str] = None
    url: Optional[str] = None
    selector: Optional[str] = None


@dataclass
class BrowserConsoleEntry:
    type: str
    text: str
    timestamp: str
    location: Optional[Dict[str, int | str]] = None


@dataclass
class BrowserArtifact:
    artifact_id: str
    kind: str
    path: str
    content_type: str
    size_bytes: int
    created_at: str
    target_id: str
    url: str
    title: str
    ref: Optional[str] = None
    suggested_filename: Optional[str] = None


@dataclass
class BrowserUploadHook:
    paths: List[str]
    ref: Optional[str] = None
    input_ref: Optional[str] = None
    timeout_ms: Optional[int] = None


@dataclass
class BrowserDialogHook:
    accept: bool
    prompt_text: Optional[str] = None
    timeout_ms: Optional[int] = None


@dataclass
class BrowserTab:
    tab_id: str
    url: str
    title: str
    profile: str
    text: str = ""
    refs: List[BrowserPageRef] = field(default_factory=list)
    console: List[BrowserConsoleEntry] = field(default_factory=list)
    artifacts: List[BrowserArtifact] = field(default_factory=list)
    cookies: List[Dict[str, object]] = field(default_factory=list)
    local_storage: Dict[str, str] = field(default_factory=dict)
    session_storage: Dict[str, str] = field(default_factory=dict)
    input_state: Dict[str, str] = field(default_factory=dict)
    uploaded_files: Dict[str, List[str]] = field(default_factory=dict)
    armed_upload: Optional[BrowserUploadHook] = None
    armed_dialog: Optional[BrowserDialogHook] = None
    last_dialog: Optional[str] = None


@dataclass(frozen=True)
class BrowserSnapshot:
    target_id: str
    url: str
    title: str
    text: str
    refs: List[BrowserPageRef]
    truncated: bool = False


@dataclass
class ProfileState:
    spec: BrowserProfileSpec
    running: bool = False
    tabs: List[BrowserTab] = field(default_factory=list)
    active_tab: Optional[str] = None


@dataclass
class BrowserServiceState:
    enabled: bool
    default_profile: str
    profiles: Dict[str, ProfileState] = field(default_factory=dict)


@dataclass
class BrowserStatus:
    running: bool
    active_profile: str
    active_tab: Optional[str]
    profile_count: int
