"""Shared callback handlers for cross-plugin navigation.

Feature-specific callbacks stay beside their owning plugin to avoid duplicate
registrations. This module handles navigation callbacks shared by multiple
features.

Branding: @Solurix_bots
"""

import logging
from contextlib import suppress

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from plugins.start import START_TEXT, main_keyboard

LOGGER = logging.getLogger("solurix.anime_downloader.callbacks")


async def _show_home(query) -> None:
    """Return the existing message to the standard start screen."""
    message = query.message
    keyboard = main_keyboard()

    try:
        if message.photo or message.video or message.document or message.animation:
            await message.edit_caption(
                caption=START_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        else:
            await message.edit_text(
                START_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
    except Exception as exc:
        # Telegram raises an error when the message already has this content,
        # or when the message type cannot be edited. Keep the bot responsive.
        LOGGER.debug("Could not edit message to home screen: %s", exc)
        with suppress(Exception):
            await message.reply_text(
                START_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )


def register_callback_handlers(app) -> None:
    """Register callbacks that connect buttons across separate plugins."""

    @app.on_callback_query(filters.regex(r"^start:home$"))
    async def start_home_callback(_client, query):
        if query.from_user is None:
            await query.answer("Could not identify your account.", show_alert=True)
            return

        await query.answer()
        await _show_home(query)

    @app.on_callback_query(filters.regex(r"^nav:close$"))
    async def shared_close_callback(_client, query):
        """Close a message only when a plugin explicitly uses nav:close."""
        await query.answer("Closed.")
        with suppress(Exception):
            await query.message.delete()

    @app.on_callback_query(filters.regex(r"^nav:help$"))
    async def shared_help_callback(_client, query):
        """Show concise help for any plugin using the shared help callback."""
        from plugins.start import HELP_TEXT

        await query.answer()
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("⌂ Home", callback_data="start:home")],
                [InlineKeyboardButton("✖ Close", callback_data="nav:close")],
            ]
        )
        try:
            if query.message.photo or query.message.video or query.message.document or query.message.animation:
                await query.message.edit_caption(
                    caption=HELP_TEXT,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            else:
                await query.message.edit_text(
                    HELP_TEXT,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
        except Exception:
            LOGGER.exception("Could not display shared help screen")
