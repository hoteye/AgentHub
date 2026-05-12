from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar


ResultT = TypeVar("ResultT")


@dataclass(slots=True, frozen=True)
class QueryBackendResult(Generic[ResultT]):
    engine: str
    result: ResultT


@dataclass(slots=True, frozen=True)
class ListDirPage:
    start_index: int
    end_index: int
    total_count: int
    selected_entries: list[dict[str, Any]]

    @property
    def truncated(self) -> bool:
        return self.end_index < self.total_count


def run_query_backend_fallback(
    *,
    rg_call: Callable[[], ResultT | None],
    python_call: Callable[[], ResultT],
) -> QueryBackendResult[ResultT]:
    rg_result = rg_call()
    if rg_result is not None:
        return QueryBackendResult(engine="rg", result=rg_result)
    return QueryBackendResult(engine="python", result=python_call())


def paginate_list_dir_entries(
    *,
    all_entries: list[dict[str, Any]],
    offset: int,
    limit: int,
    file_tool_error_cls: type[Exception],
) -> ListDirPage:
    total_count = len(all_entries)
    if total_count == 0:
        return ListDirPage(
            start_index=0,
            end_index=0,
            total_count=0,
            selected_entries=[],
        )
    start_index = int(offset) - 1
    if start_index >= total_count:
        raise file_tool_error_cls("offset exceeds directory entry count")
    end_index = min(total_count, start_index + int(limit))
    return ListDirPage(
        start_index=start_index,
        end_index=end_index,
        total_count=total_count,
        selected_entries=all_entries[start_index:end_index],
    )


__all__ = [
    "ListDirPage",
    "QueryBackendResult",
    "paginate_list_dir_entries",
    "run_query_backend_fallback",
]
