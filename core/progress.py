"""Progress formatting and throttled Telegram status updates.

This module is intentionally independent of the downloader and uploader so
both can report progress using the same helpers.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

ProgressCallback = Callable[[int, int], Awaitable[None] | None]


def human_bytes(value: int | float) -> str:
    """Format a byte count using readable binary units."""
    amount = max(0.0, float(value))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} TB"


def progress_bar(current: int, total: int, *, width: int = 12) -> str:
    """Return a compact text progress bar."""
    if width < 1:
        raise ValueError("width must be at least 1")
    ratio = 0.0 if total <= 0 else min(1.0, max(0.0, current / total))
    filled = int(ratio * width)
    return "▰" * filled + "▱" * (width - filled)


def progress_text(
    current: int,
    total: int,
    *,
    title: str = "Processing",
    speed: float | None = None,
    eta: float | None = None,
    width: int = 12,
) -> str:
    """Build a concise status message suitable for Telegram."""
    current = max(0, current)
    total = max(0, total)
    percent = 0.0 if total <= 0 else min(100.0, current * 100 / total)
    lines = [
        f"**{title}**",
        f"{progress_bar(current, total, width=width)}  `{percent:.1f}%`",
        f"{human_bytes(current)} / {human_bytes(total)}",
    ]
    if speed is not None and speed > 0:
        lines.append(f"Speed: {human_bytes(speed)}/s")
    if eta is not None and eta >= 0:
        seconds = int(eta)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            eta_text = f"{hours}h {minutes}m"
        elif minutes:
            eta_text = f"{minutes}m {seconds}s"
        else:
            eta_text = f"{seconds}s"
        lines.append(f"ETA: {eta_text}")
    return "\n".join(lines)


@dataclass(slots=True)
class ProgressTracker:
    """Track transfer speed and estimate remaining time."""

    total: int
    started_at: float = 0.0
    current: int = 0
    _last_bytes: int = 0
    _last_time: float = 0.0
    speed: float = 0.0

    def __post_init__(self) -> None:
        now = time.monotonic()
        self.started_at = self.started_at or now
        self._last_time = now
        self.total = max(0, self.total)

    def update(self, current: int) -> tuple[float, float | None]:
        """Update byte count; return (average speed, ETA seconds)."""
        now = time.monotonic()
        self.current = max(0, current)
        elapsed = now - self._last_time
        if elapsed > 0:
            instant_speed = max(0, self.current - self._last_bytes) / elapsed
            self.speed = instant_speed if self.speed <= 0 else (self.speed * 0.65 + instant_speed * 0.35)
        self._last_bytes = self.current
        self._last_time = now
        eta = None
        if self.speed > 0 and self.total > self.current:
            eta = (self.total - self.current) / self.speed
        return self.speed, eta

    def render(self, *, title: str = "Processing") -> str:
        return progress_text(
            self.current,
            self.total,
            title=title,
            speed=self.speed,
            eta=(self.total - self.current) / self.speed if self.speed > 0 and self.total > self.current else None,
        )


class ThrottledProgress:
    """Wrap a callback so frequent transfer events do not spam Telegram edits."""

    def __init__(
        self,
        callback: ProgressCallback,
        *,
        min_interval: float = 2.0,
        min_delta: int = 256 * 1024,
    ) -> None:
        if min_interval < 0 or min_delta < 0:
            raise ValueError("throttle limits cannot be negative")
        self.callback = callback
        self.min_interval = min_interval
        self.min_delta = min_delta
        self._last_time = 0.0
        self._last_current = -1
        self._lock = asyncio.Lock()

    async def __call__(self, current: int, total: int) -> None:
        current = max(0, current)
        total = max(0, total)
        async with self._lock:
            now = time.monotonic()
            finished = total > 0 and current >= total
            if (
                not finished
                and self._last_current >= 0
                and now - self._last_time < self.min_interval
                and current - self._last_current < self.min_delta
            ):
                return
            self._last_time = now
            self._last_current = current
            result = self.callback(current, total)
            if asyncio.iscoroutine(result):
                await result


__all__ = [
    "ProgressTracker",
    "ThrottledProgress",
    "human_bytes",
    "progress_bar",
    "progress_text",
]
