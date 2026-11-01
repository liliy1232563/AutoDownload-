"""Async download-job lifecycle manager for Anime Auto Downloader.

This module manages jobs in process memory. Persistent storage and recovery
across restarts are handled separately by the database layer.

Branding: @Solurix_bots
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}


@dataclass(slots=True)
class DownloadJob:
    job_id: str
    user_id: int
    source_url: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    message: str = "Waiting in queue"
    result_path: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a serialization-friendly snapshot."""
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "source_url": self.source_url,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result_path": self.result_path,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metadata": dict(self.metadata),
        }


class JobManager:
    """Manage queued jobs with bounded concurrency and safe state updates."""

    def __init__(self, max_concurrent: int = 2, max_queue_size: int = 100) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be at least 1")

        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max_queue_size)
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent

    async def create_job(
        self,
        user_id: int,
        source_url: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> DownloadJob:
        """Create and enqueue a job, rejecting a full queue."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not isinstance(source_url, str) or not source_url.strip():
            raise ValueError("source_url must be a non-empty string")

        async with self._lock:
            if self._queue.full():
                raise asyncio.QueueFull("The download queue is currently full")

            job = DownloadJob(
                job_id=uuid.uuid4().hex,
                user_id=user_id,
                source_url=source_url.strip(),
                metadata=dict(metadata or {}),
            )
            self._jobs[job.job_id] = job
            self._queue.put_nowait(job.job_id)
            logger.info("Created download job %s for user %s", job.job_id, user_id)
            return job

    async def next_job(self) -> DownloadJob | None:
        """Wait for the next queued job and mark it as running."""
        while True:
            job_id = await self._queue.get()
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status != JobStatus.QUEUED:
                    self._queue.task_done()
                    continue
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                job.message = "Download started"
                return job

    async def update_progress(
        self, job_id: str, progress: float, message: str | None = None
    ) -> DownloadJob:
        """Update progress for a running job; progress is clamped to 0–100."""
        value = float(progress)
        if not 0 <= value <= 100:
            raise ValueError("progress must be between 0 and 100")
        async with self._lock:
            job = self._require_job(job_id)
            self._require_running(job)
            job.progress = value
            if message is not None:
                job.message = str(message)[:300]
            return job

    async def complete_job(self, job_id: str, result_path: str | None = None) -> DownloadJob:
        async with self._lock:
            job = self._require_job(job_id)
            self._require_running(job)
            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.message = "Completed"
            job.result_path = result_path
            job.finished_at = time.time()
            self._queue.task_done()
            return job

    async def fail_job(self, job_id: str, error: str) -> DownloadJob:
        async with self._lock:
            job = self._require_job(job_id)
            self._require_running(job)
            job.status = JobStatus.FAILED
            job.error = str(error)[:1000]
            job.message = "Failed"
            job.finished_at = time.time()
            self._queue.task_done()
            logger.warning("Download job %s failed: %s", job_id, job.error)
            return job

    async def cancel_job(self, job_id: str, *, requester_id: int) -> DownloadJob:
        """Cancel a queued job owned by requester; running jobs need worker cancellation."""
        async with self._lock:
            job = self._require_job(job_id)
            if job.user_id != requester_id:
                raise PermissionError("You cannot cancel another user's job")
            if job.status != JobStatus.QUEUED:
                raise ValueError("Only queued jobs can be cancelled here")
            job.status = JobStatus.CANCELLED
            job.message = "Cancelled"
            job.finished_at = time.time()
            return job

    async def get_job(self, job_id: str) -> DownloadJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_user_jobs(self, user_id: int, limit: int = 20) -> list[DownloadJob]:
        if limit < 1:
            return []
        async with self._lock:
            jobs = [job for job in self._jobs.values() if job.user_id == user_id]
            return sorted(jobs, key=lambda item: item.created_at, reverse=True)[:limit]

    async def queue_size(self) -> int:
        return self._queue.qsize()

    async def wait_for_capacity(self) -> asyncio.Semaphore:
        """Return the concurrency semaphore for use with `async with`."""
        return self._semaphore

    def _require_job(self, job_id: str) -> DownloadJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        return job

    @staticmethod
    def _require_running(job: DownloadJob) -> None:
        if job.status != JobStatus.RUNNING:
            raise ValueError(f"Job {job.job_id} is not running")


# Shared in-process manager. Configure limits from application settings at startup
# if a deployment needs values other than these conservative defaults.
job_manager = JobManager(max_concurrent=2, max_queue_size=100)
