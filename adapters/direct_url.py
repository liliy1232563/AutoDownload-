"""Adapter for direct, publicly accessible HTTP(S) media URLs."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from core.download_engine import DownloadEngine, DownloadResult, download_engine
from core.url_validator import UnsafeURL, validate_url


class DirectURLAdapter:
    """Validate and download direct media links from arbitrary public hosts.

    This adapter is selected by URL/content detection, not registered in the
    hostname-based SourceRegistry (direct files can be hosted anywhere).
    """

    name = "direct-url"
    hosts: tuple[str, ...] = ()

    MEDIA_EXTENSIONS = {
        ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi",
        ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav",
        ".ts", ".m3u8", ".mpd", ".zip", ".rar", ".7z",
    }

    def __init__(self, engine: DownloadEngine | None = None) -> None:
        self.engine = engine or download_engine

    @classmethod
    def can_handle(cls, url: str, content_type: str | None = None) -> bool:
        try:
            parts = urlsplit(url)
            if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
                return False
        except (TypeError, ValueError):
            return False
        if content_type and (
            content_type.lower().startswith(("video/", "audio/"))
            or content_type.lower() in {"application/octet-stream", "application/zip"}
        ):
            return True
        return Path(unquote(parts.path)).suffix.lower() in cls.MEDIA_EXTENSIONS

    async def extract(self, url: str) -> dict[str, Any]:
        """Return a validated direct URL and basic filename metadata."""
        try:
            validated = await validate_url(url)
        except UnsafeURL:
            raise
        path_name = Path(unquote(urlsplit(validated.url).path)).name
        filename = path_name or "download.bin"
        guessed_type, _ = mimetypes.guess_type(filename)
        return {
            "source": self.name,
            "title": filename,
            "filename": filename,
            "media_url": validated.url,
            "webpage_url": validated.url,
            "content_type": guessed_type or "application/octet-stream",
            "extractor": self.name,
        }

    async def download(
        self,
        url: str,
        destination: str | Path,
        *,
        filename: str | None = None,
        max_bytes: int | None = None,
        progress=None,
    ) -> DownloadResult:
        """Download a direct link using the shared SSRF-safe engine."""
        return await self.engine.download(
            url, destination, filename=filename, max_bytes=max_bytes, progress=progress
        )


direct_url_adapter = DirectURLAdapter()
