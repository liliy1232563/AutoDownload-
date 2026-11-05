"""Source adapters: turn a user link into something the downloader can fetch.

To add your own legal source: subclass SourceAdapter, implement matches() and
resolve(), then call register(YourAdapter()) at the bottom of this file.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, unquote, urlparse

import aiohttp
import yt_dlp

LOGGER = logging.getLogger("solurix.anime_downloader.adapters")
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".ogv")


@dataclass
class Resolved:
    url: str
    title: str
    duration: Optional[float] = None
    source: str = "generic"


class SourceAdapter:
    name = "base"

    def matches(self, url: str) -> bool:
        raise NotImplementedError

    async def resolve(self, url: str) -> Resolved:
        raise NotImplementedError


class DirectLinkAdapter(SourceAdapter):
    """Direct .mp4 / .mkv / .webm file links."""

    name = "Direct link"

    def matches(self, url):
        return urlparse(url).path.lower().endswith(VIDEO_EXT)

    async def resolve(self, url):
        filename = unquote(os.path.basename(urlparse(url).path))
        title = os.path.splitext(filename)[0] or "Video"
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url, allow_redirects=True) as resp:
                if resp.status >= 400 and resp.status not in (405, 501):
                    raise RuntimeError(f"Server replied with status {resp.status}")
        return Resolved(url, title, None, self.name)


class ArchiveOrgAdapter(SourceAdapter):
    """archive.org item pages (public domain / Creative Commons uploads)."""

    name = "archive.org"
    pattern = re.compile(r"^https?://(?:www\.)?archive\.org/(?:details|download)/([^/?#]+)")

    def matches(self, url):
        return bool(self.pattern.match(url))

    async def resolve(self, url):
        ident = self.pattern.match(url).group(1)
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://archive.org/metadata/{ident}") as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"archive.org replied with status {resp.status}")
                data = await resp.json(content_type=None)

        videos = [
            f for f in data.get("files", [])
            if f.get("name", "").lower().endswith(VIDEO_EXT)
        ]
        if not videos:
            raise RuntimeError("No video file found in this archive.org item")

        best = max(videos, key=lambda f: int(f.get("size") or 0))
        title = data.get("metadata", {}).get("title") or ident
        if isinstance(title, list):
            title = title[0]
        file_url = f"https://archive.org/download/{ident}/{quote(best['name'])}"
        return Resolved(file_url, str(title), None, self.name)


def _extract(url: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


class YtDlpAdapter(SourceAdapter):
    """Fallback: any site that yt-dlp officially supports."""

    name = "yt-dlp"

    def matches(self, url):
        return True

    async def resolve(self, url):
        info = await asyncio.to_thread(_extract, url)
        return Resolved(url, info.get("title") or "Video", info.get("duration"), self.name)


ADAPTERS: list = []


def register(adapter: SourceAdapter, first: bool = False) -> None:
    if first:
        ADAPTERS.insert(0, adapter)
    else:
        ADAPTERS.append(adapter)


async def resolve_url(url: str) -> Resolved:
    """Try every matching adapter in order; the first success wins."""
    last_error = None
    for adapter in ADAPTERS:
        if not adapter.matches(url):
            continue
        try:
            return await adapter.resolve(url)
        except Exception as exc:
            LOGGER.warning("Adapter %s failed: %s", adapter.name, exc)
            last_error = exc
    raise last_error or RuntimeError("No adapter could handle this link")


register(DirectLinkAdapter())
register(ArchiveOrgAdapter())
register(YtDlpAdapter())
