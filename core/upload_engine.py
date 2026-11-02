"""Telegram upload helper for Anime Auto Downloader.

Uploads completed local files through a running Pyrogram client. This module
only sends files to chats/channels where the bot has permission; it does not
attempt to bypass Telegram limits or channel access controls.

Branding: @Solurix_bots
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from pyrogram import Client
from pyrogram.types import Message

logger = logging.getLogger(__name__)
UploadProgress = Callable[[int, int], Awaitable[None] | None]


class UploadError(RuntimeError):
    """Raised when a file cannot be uploaded to Telegram."""


@dataclass(frozen=True, slots=True)
class UploadResult:
    chat_id: int | str
    message_id: int
    file_id: str | None
    file_name: str
    size: int
    media_type: str


class UploadEngine:
    """Upload local files as Telegram documents, videos, or audio."""

    def __init__(self, *, max_bytes: int = 2_000_000_000) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be a positive integer")
        self.max_bytes = max_bytes

    async def upload(
        self,
        client: Client,
        chat_id: int | str,
        file_path: str | Path,
        *,
        caption: str | None = None,
        thumb: str | Path | None = None,
        media_type: str = "document",
        progress: UploadProgress | None = None,
        reply_to_message_id: int | None = None,
        disable_notification: bool = False,
        protect_content: bool = False,
        max_bytes: int | None = None,
    ) -> UploadResult:
        """Upload a file and return its Telegram message/file details.

        ``progress`` receives ``(uploaded_bytes, total_bytes)``. Supported
        media types are ``document``, ``video`` and ``audio``. The caller owns
        file cleanup; this method never deletes the source file.
        """
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise UploadError("The file does not exist or is not a regular file.")
        if media_type not in {"document", "video", "audio"}:
            raise ValueError("media_type must be document, video, or audio")

        limit = self.max_bytes if max_bytes is None else max_bytes
        if limit < 1:
            raise ValueError("max_bytes must be a positive integer")
        size = path.stat().st_size
        if size <= 0:
            raise UploadError("The file is empty.")
        if size > limit:
            raise UploadError("The file exceeds the configured upload size limit.")

        thumb_path: str | None = None
        if thumb is not None:
            candidate = Path(thumb).expanduser().resolve()
            if not candidate.is_file():
                raise UploadError("The thumbnail file does not exist.")
            thumb_path = str(candidate)

        async def progress_callback(current: int, total: int, *_: object) -> None:
            if progress is None:
                return
            try:
                result = progress(current, total)
                if asyncio.iscoroutine(result):
                    await result
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Upload progress callback failed")

        kwargs: dict[str, object] = {
            "chat_id": chat_id,
            "caption": (caption or "")[:1024],
            "thumb": thumb_path,
            "reply_to_message_id": reply_to_message_id,
            "disable_notification": disable_notification,
            "protect_content": protect_content,
            "progress": progress_callback if progress is not None else None,
        }

        method = {
            "document": client.send_document,
            "video": client.send_video,
            "audio": client.send_audio,
        }[media_type]
        file_argument = {"document": str(path)} if media_type == "document" else (
            {"video": str(path)} if media_type == "video" else {"audio": str(path)}
        )

        try:
            message: Message = await method(**file_argument, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Telegram upload failed for %s", path.name)
            raise UploadError(f"Telegram upload failed: {exc}") from exc

        media = message.document or message.video or message.audio
        file_id = getattr(media, "file_id", None) if media else None
        logger.info("Uploaded %s (%s bytes) to %s", path.name, size, chat_id)
        return UploadResult(
            chat_id=chat_id,
            message_id=message.id,
            file_id=file_id,
            file_name=path.name,
            size=size,
            media_type=media_type,
        )


upload_engine = UploadEngine()
