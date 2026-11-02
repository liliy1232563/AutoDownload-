"""Safe temporary-file cleanup utilities for Anime Auto Downloader.

Only paths inside the configured work directory are eligible for cleanup.
The module never follows symlinks and never removes the work directory itself.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CleanupResult:
    deleted_files: int = 0
    deleted_directories: int = 0
    deleted_bytes: int = 0
    errors: int = 0


class CleanupManager:
    """Clean stale files and job folders below one dedicated work directory."""

    def __init__(
        self,
        work_dir: str | Path,
        *,
        max_age_seconds: int = 24 * 60 * 60,
        protected_names: Iterable[str] = (),
    ) -> None:
        root = Path(work_dir).expanduser().resolve()
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds cannot be negative")
        self.work_dir = root
        self.max_age_seconds = max_age_seconds
        self.protected_names = set(protected_names)

    def _is_within_root(self, path: Path) -> bool:
        try:
            path.relative_to(self.work_dir)
            return path != self.work_dir
        except ValueError:
            return False

    @staticmethod
    def _tree_size(path: Path) -> int:
        if path.is_symlink():
            return 0
        if path.is_file():
            try:
                return path.stat().st_size
            except OSError:
                return 0
        total = 0
        if path.is_dir():
            try:
                for child in path.iterdir():
                    if not child.is_symlink():
                        total += CleanupManager._tree_size(child)
            except OSError:
                pass
        return total

    def _remove_path(self, path: Path) -> tuple[int, int, int]:
        """Remove one eligible path; return (files, dirs, bytes)."""
        if not self._is_within_root(path) or path.name in self.protected_names:
            return (0, 0, 0)
        if path.is_symlink():
            # Unlink the symlink itself; never traverse its target.
            path.unlink()
            return (1, 0, 0)
        size = self._tree_size(path)
        if path.is_dir():
            file_count = sum(1 for p in path.rglob("*") if p.is_file() and not p.is_symlink())
            dir_count = sum(1 for p in path.rglob("*") if p.is_dir() and not p.is_symlink()) + 1
            shutil.rmtree(path)
            return (file_count, dir_count, size)
        if path.is_file():
            path.unlink()
            return (1, 0, size)
        return (0, 0, 0)

    def cleanup_stale(self, *, now: float | None = None) -> CleanupResult:
        """Delete files/directories older than max_age_seconds, recursively."""
        if not self.work_dir.exists():
            return CleanupResult()
        if self.work_dir.is_symlink() or not self.work_dir.is_dir():
            raise ValueError("work_dir must be a real directory, not a symlink")

        current = time.time() if now is None else now
        cutoff = current - self.max_age_seconds
        files = dirs = size = errors = 0

        # Snapshot children before deletion; skip symlink traversal.
        try:
            children = list(self.work_dir.iterdir())
        except OSError:
            logger.exception("Could not list cleanup directory %s", self.work_dir)
            return CleanupResult(errors=1)

        for child in children:
            if child.name in self.protected_names:
                continue
            try:
                if child.is_symlink():
                    modified = child.lstat().st_mtime
                else:
                    modified = child.stat().st_mtime
                if modified >= cutoff:
                    continue
                f_count, d_count, byte_count = self._remove_path(child)
                files += f_count
                dirs += d_count
                size += byte_count
            except FileNotFoundError:
                continue
            except OSError:
                errors += 1
                logger.exception("Failed to clean %s", child)

        return CleanupResult(files, dirs, size, errors)

    def remove_job(self, job_id: str) -> CleanupResult:
        """Remove a single job folder named by a conservative job identifier."""
        if not job_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in job_id):
            raise ValueError("job_id contains unsupported characters")
        target = self.work_dir / job_id
        if not target.exists() and not target.is_symlink():
            return CleanupResult()
        try:
            files, dirs, size = self._remove_path(target)
            return CleanupResult(files, dirs, size, 0)
        except OSError:
            logger.exception("Failed to remove job directory %s", target)
            return CleanupResult(errors=1)

    async def cleanup_stale_async(self, *, now: float | None = None) -> CleanupResult:
        """Run cleanup without blocking the bot's event loop."""
        return await asyncio.to_thread(self.cleanup_stale, now=now)

    async def remove_job_async(self, job_id: str) -> CleanupResult:
        """Remove a job folder without blocking the bot's event loop."""
        return await asyncio.to_thread(self.remove_job, job_id)


# Convenience factory; instantiate with the configured download/work path.
def create_cleanup_manager(work_dir: str | Path, *, max_age_seconds: int = 86400) -> CleanupManager:
    return CleanupManager(work_dir, max_age_seconds=max_age_seconds)
