"""Secure direct-media URL downloader for Anime Auto Downloader.

Only publicly reachable direct media URLs are supported here. Website-specific
adapters can be added separately when their terms and access rules permit it.
Branding: @Solurix_bots
"""

import asyncio
import ipaddress
import html
import logging
import mimetypes
import os
import socket
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver
from pyrogram import filters
from pyrogram.enums import ParseMode

LOGGER = logging.getLogger("solurix.anime_downloader.downloader")
MAX_FILE_SIZE = int(os.getenv("MAX_DOWNLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
CHUNK_SIZE = 1024 * 1024
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60 * 60, connect=20, sock_connect=20, sock_read=90)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".mpeg", ".mpg", ".ts"}


class UnsafeURL(ValueError):
    """Raised when a URL is not safe to fetch."""


class PinnedResolver(AbstractResolver):
    """Resolve only the already-validated public addresses for one hostname."""

    def __init__(self, hostname: str, addresses: list[str]):
        self.hostname = hostname.lower().rstrip(".")
        self.addresses = addresses

    async def resolve(self, host, port=0, family=socket.AF_INET):
        if host.lower().rstrip(".") != self.hostname:
            raise OSError("Unexpected hostname requested by HTTP client")
        records = []
        for address in self.addresses:
            ip = ipaddress.ip_address(address)
            records.append({
                "hostname": host,
                "host": address,
                "port": port,
                "family": socket.AF_INET6 if ip.version == 6 else socket.AF_INET,
                "proto": 0,
                "flags": 0,
            })
        return records

    async def close(self):
        return None


async def _validate_and_resolve(url: str) -> tuple[str, list[str]]:
    """Allow only HTTP(S) public hosts and pin DNS results to prevent SSRF."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise UnsafeURL("Invalid URL format.") from exc

    if parts.scheme.lower() not in {"http", "https"}:
        raise UnsafeURL("Please send a direct HTTP or HTTPS media link.")
    if not parts.hostname or parts.username or parts.password:
        raise UnsafeURL("That link is not valid.")
    if port not in (None, 80, 443):
        raise UnsafeURL("Links using custom ports are not supported.")

    hostname = parts.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".local", ".internal", ".localhost")):
        raise UnsafeURL("Private or local network links are not allowed.")

    try:
        literal_ip = ipaddress.ip_address(hostname)
        addresses = [str(literal_ip)]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(hostname, port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except (OSError, socket.gaierror) as exc:
            raise UnsafeURL("Could not resolve the link's host.") from exc
        addresses = list(dict.fromkeys(info[4][0] for info in infos))

    if not addresses:
        raise UnsafeURL("The link's host did not resolve.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise UnsafeURL("Private or non-public network addresses are not allowed.")
    return hostname, addresses


async def _open_validated(url: str):
    """Open one URL without automatic redirects, using pinned public DNS."""
    hostname, addresses = await _validate_and_resolve(url)
    resolver = PinnedResolver(hostname, addresses)
    connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False, limit=4)
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "AnimeAutoDownloader/1.0 (+@Solurix_bots)"},
        trust_env=False,
    )
    try:
        response = await session.get(url, allow_redirects=False)
    except Exception:
        await session.close()
        raise
    return session, response


async def _download_to_temp(url: str) -> tuple[str, str, str, int]:
    """Stream a supported direct media response to a temporary file."""
    current_url = url
    session = response = None
    for redirect_count in range(MAX_REDIRECTS + 1):
        session, response = await _open_validated(current_url)
        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.release()
            await session.close()
            if not location or redirect_count >= MAX_REDIRECTS:
                raise UnsafeURL("Too many redirects or an invalid redirect response.")
            current_url = urljoin(current_url, location)
            continue
        break

    assert session is not None and response is not None
    temp_path = None
    try:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"The source server returned HTTP {response.status}.")

        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        final_path = urlsplit(str(response.url)).path
        suffix = Path(final_path).suffix.lower()
        is_video = content_type.startswith("video/") or suffix in VIDEO_EXTENSIONS
        if not is_video and not (content_type in {"application/octet-stream", "binary/octet-stream"} and suffix in VIDEO_EXTENSIONS):
            raise RuntimeError("This link does not appear to point directly to a video file.")
        if suffix not in VIDEO_EXTENSIONS:
            guessed = mimetypes.guess_extension(content_type) if content_type.startswith("video/") else None
            suffix = guessed if guessed in VIDEO_EXTENSIONS else ".mp4"

        content_length = response.content_length
        if content_length is not None and content_length > MAX_FILE_SIZE:
            raise RuntimeError(f"File is larger than the configured limit ({MAX_FILE_SIZE // (1024 * 1024)} MB).")

        handle = tempfile.NamedTemporaryFile(prefix="aad_", suffix=suffix, delete=False)
        temp_path = handle.name
        total = 0
        with handle:
            async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise RuntimeError(f"File exceeded the configured limit ({MAX_FILE_SIZE // (1024 * 1024)} MB).")
                handle.write(chunk)
        if total == 0:
            raise RuntimeError("The source returned an empty file.")
        return temp_path, suffix, content_type, total
    except Exception:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise
    finally:
        response.release()
        await session.close()


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def register_downloader_handlers(app) -> None:
    """Register private-chat direct video URL handling."""

    @app.on_message(filters.private & filters.text & ~filters.command([
        "start", "help", "about", "stats", "addadmin", "deladmin", "adminlist"
    ]))
    async def handle_video_url(client, message):
        raw_text = (message.text or "").strip()
        parts = raw_text.split()
        if len(parts) != 1 or not raw_text.lower().startswith(("http://", "https://")):
            return

        status = await message.reply_text(
            "<b>Checking link...</b>\nPlease wait while I verify the source.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        temp_path = None
        try:
            temp_path, suffix, content_type, size = await _download_to_temp(raw_text)
            await status.edit_text(
                f"<b>Download complete</b>\nSize: <code>{_human_size(size)}</code>\nUploading to Telegram...",
                parse_mode=ParseMode.HTML,
            )

            last_update = 0.0

            async def progress(current: int, total: int, *args):
                nonlocal last_update
                now = time.monotonic()
                if total > 0 and (current >= total or now - last_update >= 5):
                    last_update = now
                    percent = min(100, int(current * 100 / total))
                    try:
                        await status.edit_text(
                            f"<b>Uploading video...</b>\n{percent}% • {_human_size(current)} / {_human_size(total)}",
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        pass

            caption = "<b>𝗔𝗻𝗶𝗺𝗲 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗲𝗿</b>\n\n<i>Powered by @Solurix_bots</i>"
            if suffix in VIDEO_EXTENSIONS:
                await client.send_video(
                    chat_id=message.chat.id,
                    video=temp_path,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    progress=progress,
                    supports_streaming=True,
                )
            else:
                await client.send_document(
                    chat_id=message.chat.id,
                    document=temp_path,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    progress=progress,
                )
            await status.delete()
        except UnsafeURL as exc:
            await status.edit_text(f"Link rejected: {exc}")
        except asyncio.TimeoutError:
            await status.edit_text("The source took too long to respond. Try another direct video link.")
        except aiohttp.ClientError:
            LOGGER.exception("Network error while processing a direct media URL")
            await status.edit_text("Could not fetch that link. Check that it is public and points directly to a video.")
        except Exception as exc:
            LOGGER.exception("Failed to process a direct media URL")
            message_text = str(exc)
            if len(message_text) > 250:
                message_text = message_text[:247] + "..."
            await status.edit_text(f"Could not process this link.\n<code>{html.escape(message_text)}</code>", parse_mode=ParseMode.HTML)
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    LOGGER.warning("Could not remove temporary download %s", temp_path)
