"""Safe asynchronous downloader for direct, publicly accessible media URLs.

This engine downloads only direct HTTP(S) resources. It does not bypass DRM,
logins, paywalls, anti-bot checks, or other access controls. Website-specific
adapters should extract a permitted direct media URL before calling it.

Branding: @Solurix_bots
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import unquote, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver

from core.url_validator import UnsafeURL, ValidatedURL, validate_url

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int, int | None], Awaitable[None] | None]


class DownloadError(RuntimeError):
    """Raised when a direct download cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: str
    filename: str
    size: int
    content_type: str
    elapsed: float
    source_url: str


class _PinnedResolver(AbstractResolver):
    """Resolve a validated hostname only to the IPs checked before connecting."""

    def __init__(self, validated: ValidatedURL) -> None:
        self._hostname = validated.hostname
        self._addresses = validated.addresses

    async def resolve(self, host: str, port: int = 0, family: int = 0):
        if host.rstrip(".").lower() != self._hostname:
            raise OSError("Unexpected hostname during connection")
        results = []
        for value in self._addresses:
            address = ipaddress.ip_address(value)
            if family not in (0, address.version == 4 and 2 or 10):
                continue
            results.append({
                "hostname": host,
                "host": value,
                "port": port,
                "family": 2 if address.version == 4 else 10,
                "proto": 0,
                "flags": 0,
            })
        if not results:
            raise OSError("No validated address matches the requested address family")
        return results

    async def close(self) -> None:
        return None


def _safe_filename(value: str, fallback: str = "download.bin") -> str:
    """Strip path components and unsafe characters from a remote filename."""
    name = unquote(value).replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[^\w.() -]", "_", name, flags=re.UNICODE)
    name = name.strip(" .")[:180]
    return name or fallback


def _filename_from_response(response: aiohttp.ClientResponse, source_url: str) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    if disposition:
        try:
            _kind, params = aiohttp.helpers.parse_content_disposition(disposition)
            candidate = params.get("filename*") or params.get("filename")
            if candidate:
                return _safe_filename(str(candidate))
        except (TypeError, ValueError):
            pass
    path_name = Path(urlsplit(source_url).path).name
    return _safe_filename(path_name, "download.bin")


class DownloadEngine:
    """Stream direct downloads to disk with SSRF, size and time safeguards."""

    def __init__(
        self,
        *,
        max_bytes: int = 1_073_741_824,
        timeout_seconds: int = 900,
        chunk_size: int = 256 * 1024,
        max_redirects: int = 5,
    ) -> None:
        if max_bytes < 1 or timeout_seconds < 1 or chunk_size < 1024:
            raise ValueError("Download limits must be positive (chunk_size >= 1024)")
        if not 0 <= max_redirects <= 10:
            raise ValueError("max_redirects must be between 0 and 10")
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds
        self.chunk_size = chunk_size
        self.max_redirects = max_redirects

    async def download(
        self,
        url: str,
        destination: str | Path,
        *,
        filename: str | None = None,
        max_bytes: int | None = None,
        progress: ProgressCallback | None = None,
    ) -> DownloadResult:
        """Download one direct URL and return its saved-file details.

        ``progress`` receives ``(downloaded_bytes, total_bytes_or_none)``.
        A failed or cancelled transfer removes its temporary partial file.
        """
        limit = self.max_bytes if max_bytes is None else max_bytes
        if limit < 1:
            raise ValueError("max_bytes must be a positive integer")

        output_dir = Path(destination).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        current_url = url
        temporary_path: Path | None = None

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds, connect=20, sock_read=60)
        headers = {"User-Agent": "AnimeAutoDownloader/1.0 (+direct-media-fetch)"}

        try:
            for redirect_count in range(self.max_redirects + 1):
                try:
                    validated = await validate_url(current_url)
                except UnsafeURL as exc:
                    raise DownloadError(str(exc)) from exc

                resolver = _PinnedResolver(validated)
                connector = aiohttp.TCPConnector(
                    resolver=resolver, use_dns_cache=False, ttl_dns_cache=0,
                    limit=1, enable_cleanup_closed=True,
                )
                async with aiohttp.ClientSession(
                    connector=connector, timeout=timeout, headers=headers,
                    trust_env=False, auto_decompress=False,
                ) as session:
                    async with session.get(
                        validated.url, allow_redirects=False
                    ) as response:
                        if response.status in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location:
                                raise DownloadError("The server returned an invalid redirect.")
                            if redirect_count >= self.max_redirects:
                                raise DownloadError("Too many redirects from the download server.")
                            current_url = str(response.url.join(aiohttp.client_reqrep.URL(location)))
                            continue

                        if response.status < 200 or response.status >= 300:
                            raise DownloadError(f"The server returned HTTP {response.status}.")

                        content_length_header = response.headers.get("Content-Length")
                        total: int | None = None
                        if content_length_header:
                            try:
                                total = int(content_length_header)
                            except ValueError:
                                raise DownloadError("The server sent an invalid file size.")
                            if total < 0 or total > limit:
                                raise DownloadError("This file exceeds the allowed download size.")

                        remote_name = filename or _filename_from_response(response, current_url)
                        safe_name = _safe_filename(remote_name)
                        # A unique prefix prevents collisions and avoids overwriting user files.
                        final_path = output_dir / f"{uuid.uuid4().hex[:10]}_{safe_name}"
                        temporary_path = final_path.with_name(final_path.name + ".part")
                        downloaded = 0
                        last_report = 0.0

                        with temporary_path.open("xb") as file_handle:
                            async for chunk in response.content.iter_chunked(self.chunk_size):
                                if not chunk:
                                    continue
                                downloaded += len(chunk)
                                if downloaded > limit:
                                    raise DownloadError("This file exceeds the allowed download size.")
                                file_handle.write(chunk)
                                now = time.monotonic()
                                if progress and (now - last_report >= 0.5 or (total and downloaded == total)):
                                    result = progress(downloaded, total)
                                    if asyncio.iscoroutine(result):
                                        await result
                                    last_report = now
                            file_handle.flush()
                            os.fsync(file_handle.fileno())

                        if downloaded == 0:
                            raise DownloadError("The server returned an empty file.")
                        temporary_path.replace(final_path)
                        temporary_path = None
                        elapsed = max(time.monotonic() - started, 0.001)
                        logger.info("Downloaded %s bytes from %s", downloaded, validated.hostname)
                        return DownloadResult(
                            path=str(final_path), filename=safe_name, size=downloaded,
                            content_type=response.headers.get("Content-Type", "application/octet-stream"),
                            elapsed=elapsed, source_url=url,
                        )

            raise DownloadError("The download could not be completed.")
        except asyncio.CancelledError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            logger.warning("Direct download failed: %s", exc)
            raise DownloadError("Network error while downloading the file.") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not remove partial download: %s", temporary_path)


# Shared default engine. Callers can create a separate instance with other limits.
download_engine = DownloadEngine()
