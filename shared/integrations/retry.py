from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Callable, Generic, Optional, Tuple, TypeVar


_T = TypeVar("_T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 1.0
    retry_statuses: Tuple[int, ...] = (429, 500, 502, 503, 504)
    retry_exception_types: Tuple[type[BaseException], ...] = field(default_factory=lambda: (TimeoutError, OSError))

    def normalized(self) -> "RetryPolicy":
        return RetryPolicy(
            max_attempts=max(1, int(self.max_attempts or 1)),
            initial_delay_seconds=max(0.0, float(self.initial_delay_seconds or 0.0)),
            backoff_multiplier=max(1.0, float(self.backoff_multiplier or 1.0)),
            max_delay_seconds=max(0.0, float(self.max_delay_seconds or 0.0)),
            retry_statuses=tuple(int(item) for item in self.retry_statuses),
            retry_exception_types=tuple(self.retry_exception_types),
        )


def retry_call(
    operation: Callable[[], _T],
    *,
    should_retry: Optional[Callable[[Optional[_T], Optional[BaseException]], bool]] = None,
    policy: Optional[RetryPolicy] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> _T:
    retry_policy = (policy or RetryPolicy()).normalized()
    attempt = 1
    delay = retry_policy.initial_delay_seconds

    while True:
        result: Optional[_T] = None
        error: Optional[BaseException] = None
        try:
            result = operation()
        except BaseException as exc:  # noqa: BLE001
            error = exc

        wants_retry = False
        if attempt < retry_policy.max_attempts:
            if should_retry is not None:
                wants_retry = bool(should_retry(result, error))
            elif error is not None:
                wants_retry = isinstance(error, retry_policy.retry_exception_types)

        if not wants_retry:
            if error is not None:
                raise error
            return result

        if delay > 0:
            sleep_fn(delay)
        attempt += 1
        if delay > 0:
            delay = min(retry_policy.max_delay_seconds, delay * retry_policy.backoff_multiplier)
        else:
            delay = retry_policy.initial_delay_seconds
