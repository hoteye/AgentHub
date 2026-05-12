from __future__ import annotations

from typing import Any


def mode_cell(item: dict[str, Any]) -> str:
    requested = str(item.get("requested_mode") or "").strip()
    effective = str(item.get("effective_mode") or "").strip()
    if requested and effective and requested != effective:
        return f"{requested}->{effective}"
    return effective or requested or "-"


def print_table(report: dict[str, Any]) -> None:
    headers = (
        "CASE",
        "BACKEND",
        "MODE",
        "SUPPORT",
        "SURFACE",
        "AVAIL",
        "DECISION",
        "MERGED",
        "MIN",
        "ALIASES_EXPOSED",
    )
    rows = [headers]
    for item in list(report.get("cases") or []):
        if not isinstance(item, dict):
            continue
        snapshot = dict(item.get("native_capability_snapshot") or {}).get("web_search")
        snapshot_map = dict(snapshot) if isinstance(snapshot, dict) else {}
        mode_matrix = dict(item.get("web_search_mode_matrix") or {})
        surface = dict(dict(item.get("provider_web_search_surface") or {}).get("merged") or {})
        alias_snapshot = dict(item.get("compatibility_alias_exposure_snapshot") or {})
        file_exposed = list(dict(alias_snapshot.get("file_tools") or {}).get("exposed_aliases") or [])
        shell_exposed = list(dict(alias_snapshot.get("shell_tools") or {}).get("exposed_aliases") or [])
        browser_exposed = list(dict(alias_snapshot.get("browser_tools") or {}).get("exposed_aliases") or [])
        alias_count = len(file_exposed) + len(shell_exposed) + len(browser_exposed)
        rows.append(
            (
                str(item.get("case") or ""),
                str(snapshot_map.get("selected_backend") or "-"),
                mode_cell(mode_matrix),
                str(mode_matrix.get("mode_support_level") or "-"),
                str(surface.get("type") or "-"),
                str(snapshot_map.get("availability") or "-"),
                str(snapshot_map.get("decision_source") or "-"),
                str(len(list(item.get("provider_merged_tools") or []))),
                str(len(list(item.get("provider_minimal_tools") or []))),
                str(alias_count),
            )
        )
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(headers))]
    for row_index, row in enumerate(rows):
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            print("  ".join("-" * width for width in widths))
