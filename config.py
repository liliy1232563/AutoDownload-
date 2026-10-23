"""Centralized environment configuration for Anime Auto Downloader.

Branding: @Solurix_bots
Keep secrets in environment variables or a local .env file; never commit them.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int = 0) -> int:
    """Read an integer environment variable without crashing on bad input."""
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_list_int(name: str) -> list[int]:
    """Parse comma-separated integer IDs, ignoring empty or invalid entries."""
    result: list[int] = []
    for item in os.getenv(name, "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            channel_id = int(item)
        except ValueError:
            continue
        if channel_id not in result:
            result.append(channel_id)
    return result


def _env_text(name: str, default: str = "") -> str:
    """Read a trimmed text setting."""
    return os.getenv(name, default).strip()


class Config:
    """Application settings loaded from environment variables."""

    # Telegram credentials
    BOT_TOKEN = _env_text("BOT_TOKEN")
    API_ID = _env_int("API_ID")
    API_HASH = _env_text("API_HASH")
    OWNER_ID = _env_int("OWNER_ID")

    # Database and hosting
    DATABASE_URL = _env_text("DATABASE_URL")
    DATABASE_NAME = _env_text("DATABASE_NAME", "AnimeAutoDownloader") or "AnimeAutoDownloader"
    PORT = _env_int("PORT", 10000)

    # Optional Telegram channels
    LOG_CHANNEL = _env_int("LOG_CHANNEL")
    FORCE_SUB_CHANNELS = _env_list_int("FORCE_SUB_CHANNELS")

    # Optional image settings: Telegram file_id or a public HTTPS image URL.
    # Leave blank to fall back to text-only messages.
    START_PIC = _env_text("START_PIC")
    HELP_PIC = _env_text("HELP_PIC")
    ABOUT_PIC = _env_text("ABOUT_PIC")
    FSUB_PIC = _env_text("FSUB_PIC")
    PREMIUM_PIC = _env_text("PREMIUM_PIC")
    DOWNLOAD_PIC = _env_text("DOWNLOAD_PIC")

    # Appearance and logging
    BRAND_NAME = "@Solurix_bots"
    BOT_NAME = _env_text("BOT_NAME", "Anime Downloader") or "Anime Downloader"
    LOG_LEVEL = _env_text("LOG_LEVEL", "INFO").upper() or "INFO"
