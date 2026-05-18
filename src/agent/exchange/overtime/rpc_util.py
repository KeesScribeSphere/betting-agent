"""RPC helpers: retries and gentle rate limiting for public endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


async def with_rpc_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 5,
    base_delay_s: float = 0.4,
) -> T:
    last: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if _is_rate_limit_error(exc) and attempt < max_attempts - 1:
                await asyncio.sleep(base_delay_s * (2**attempt))
                continue
            raise
    raise last  # type: ignore[misc]
