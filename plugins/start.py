"""Start screen and basic navigation for Anime Auto Downloader.

Branding: @Solurix_bots
"""

import logging
from contextlib import suppress

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config

LOGGER = logging.getLogger("solurix.anime_downloader.start")

START_TEXT = (
    "<b>𝗔𝗻𝗶𝗺𝗲 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗲𝗿</b>\n\n"
    "Welcome! Send an anime episode link to get started.\n\n"
    "<i>Fast • Simple • Reliable</i>\n\n"
    "<i>Powered by @Solurix_bots</i>"
)

HELP_TEXT = (
    "<b>𝗛𝗲𝗹𝗽</b>\n\n"
    "1. Send a supported anime episode URL or a direct video link.\n"
    "2. Wait while the bot checks the link.\n"
    "3. Follow the available download options.\n\n"
    "Only supported, publicly accessible links can be processed."
)

ABOUT_TEXT = (
    "<b>𝗔𝗯𝗼𝘂𝘁</b>\n\n"
    "An anime link assistant built for simple downloads and a clean experience.\n\n"
    "<i>Powered by @Solurix_bots</i>"
)


def main_keyboard() -> InlineKeyboardMarkup:
    """Build the start-screen keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📚 Help", callback_data="aad:help"),
                InlineKeyboardButton("ⓘ About", callback_data="aad:about"),
            ],
            [InlineKeyboardButton("✖ Close", callback_data="aad:close")],
        ]
    )


def _display_photo(value: str) -> bool:
    """Return True when a photo value is configured."""
    return bool(value and value.strip())


async def _send_start(message) -> None:
    """Send the start message with an optional configured image."""
    if _display_photo(Config.START_PIC):
        try:
            await message.reply_photo(
                photo=Config.START_PIC,
                caption=START_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
            )
            return
        except Exception as exc:
            LOGGER.warning("START_PIC could not be sent; using text fallback: %s", exc)

    await message.reply_text(
        START_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


def register_start_handlers(app) -> None:
    """Register /start and the start screen's navigation callbacks."""

    @app.on_message(filters.command("start") & filters.private)
    async def start_command(_client, message):
        try:
            await _send_start(message)
        except Exception:
            LOGGER.exception("Failed to send the start screen")
            with suppress(Exception):
                await message.reply_text(
                    "Something went wrong. Please try /start again.",
                    reply_markup=main_keyboard(),
                )

    @app.on_callback_query(filters.regex(r"^aad:(help|about|home|close)$"))
    async def navigation_callback(_client, query):
        data = query.data.split(":", maxsplit=1)[1]
        if data == "close":
            await query.answer("Closed.")
            with suppress(Exception):
                await query.message.delete()
            return

        await query.answer()
        if data == "help":
            text = HELP_TEXT
        elif data == "about":
            text = ABOUT_TEXT
        else:
            text = START_TEXT

        keyboard = main_keyboard()
        if data != "home":
            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("⌂ Home", callback_data="aad:home")],
                    [InlineKeyboardButton("✖ Close", callback_data="aad:close")],
                ]
            )

        try:
            if query.message.photo or query.message.video or query.message.document:
                await query.message.edit_caption(
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            else:
                await query.message.edit_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
        except Exception as exc:
            # Avoid failing on an unchanged message or an unsupported edit.
            LOGGER.debug("Navigation edit was not applied: %s", exc)

