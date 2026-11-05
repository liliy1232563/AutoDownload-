import html
import logging
from contextlib import suppress

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config

LOGGER = logging.getLogger("solurix.anime_downloader.start")


def start_text(name):
    return (
        "✨ <b>𝗔𝗡𝗜𝗠𝗘 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗𝗘𝗥</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 Hey <b>{html.escape(name)}</b>!\n\n"
        "📥 Send me a link, pick a quality and I'll\n"
        "     download it with a <b>live progress bar</b>.\n"
        "📡 Connect your channel and I'll upload\n"
        "     every file there <b>automatically</b>.\n\n"
        "⚡ <i>Fast  •  Smooth  •  Premium</i>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Powered by @Solurix_bots</i>"
    )


HELP_TEXT = (
    "📚 <b>𝗛𝗢𝗪 𝗧𝗢 𝗨𝗦𝗘</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "<b>1️⃣ Download</b>\n"
    "Send a supported episode link or a direct video link,\n"
    "then choose the quality.\n\n"
    "<b>2️⃣ Add your channel</b>\n"
    "Make the bot <b>Admin</b> in your channel, then send:\n"
    "<code>/addchannel @yourchannel</code>\n\n"
    "<b>3️⃣ Choose default channel</b>\n"
    "/channels → tap a channel to set ⭐\n\n"
    "<b>Commands</b>\n"
    "/start • /addchannel • /channels\n\n"
    "<i>Only supported, publicly accessible links can be processed.</i>"
)

ABOUT_TEXT = (
    "ⓘ <b>𝗔𝗕𝗢𝗨𝗧</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "A fast anime link assistant with queue, live progress\n"
    "and automatic channel uploads.\n\n"
    "<i>Powered by @Solurix_bots</i>"
)


def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📡 My Channels", callback_data="aad:channels"),
            InlineKeyboardButton("📚 Help", callback_data="aad:help"),
        ],
        [
            InlineKeyboardButton("ⓘ About", callback_data="aad:about"),
            InlineKeyboardButton("🌟 Support", url="https://t.me/Solurix_bots"),
        ],
        [InlineKeyboardButton("✖ Close", callback_data="aad:close")],
    ])


def _display_photo(value):
    return bool(value and value.strip())


async def _send_start(message):
    name = message.from_user.first_name if message.from_user else "there"
    text = start_text(name)
    if _display_photo(Config.START_PIC):
        try:
            await message.reply_photo(
                photo=Config.START_PIC, caption=text,
                parse_mode=ParseMode.HTML, reply_markup=main_keyboard(),
            )
            return
        except Exception as exc:
            LOGGER.warning("START_PIC could not be sent; using text fallback: %s", exc)
    await message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(), disable_web_page_preview=True,
    )


def register_start_handlers(app):
    @app.on_message(filters.command("start") & filters.private)
    async def start_command(_client, message):
        try:
            await _send_start(message)
        except Exception:
            LOGGER.exception("Failed to send the start screen")
            with suppress(Exception):
                await message.reply_text("Something went wrong. Please try /start again.", reply_markup=main_keyboard())

    @app.on_message(filters.command("help") & filters.private)
    async def help_command(_client, message):
        await message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    @app.on_message(filters.command("about") & filters.private)
    async def about_command(_client, message):
        await message.reply_text(ABOUT_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

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
            text = start_text(query.from_user.first_name or "there")
        keyboard = main_keyboard()
        if data != "home":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⌂ Home", callback_data="aad:home")],
                [InlineKeyboardButton("✖ Close", callback_data="aad:close")],
            ])
        try:
            if query.message.photo or query.message.video or query.message.document:
                await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            else:
                await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
        except Exception as exc:
            LOGGER.debug("Navigation edit was not applied: %s", exc)


START_TEXT = start_text("there")
