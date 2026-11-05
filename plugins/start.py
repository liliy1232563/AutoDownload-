"""Start screen: About + Help, premium small-caps font."""

import html
import logging
from contextlib import suppress

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton as Btn
from pyrogram.types import InlineKeyboardMarkup as Markup

from config import Config
from plugins.premium import is_owner
from plugins.style import sc

LOGGER = logging.getLogger("solurix.anime_downloader.start")
LINE = "━━━━━━━━━━━━━━━━━━"


def start_text(name):
    return (
        "✨ <b>" + sc("anime downloader") + "</b> ✨\n"
        + LINE + "\n\n"
        + "👋 " + sc("hey") + f" <b>{html.escape(name)}</b>!\n\n"
        + "➲ " + sc("send a link and pick a quality") + "\n"
        + "➲ " + sc("live progress bar while it downloads") + "\n"
        + "➲ " + sc("auto upload to your own channel") + "\n\n"
        + "⚡ <i>" + sc("fast • smooth • premium") + "</i>\n"
        + LINE + "\n"
        + "<i>" + sc("powered by") + " @Solurix_bots</i>"
    )


def help_text(owner=False):
    text = (
        "<b>" + sc("here is help menu:") + "</b>\n\n"
        + "📥 " + sc("send a link, then choose a quality.") + "\n\n"
        + "➲ /settings: " + sc("upload type, thumbnail, caption") + "\n"
        + "➲ /metadata: " + sc("edit file metadata tags") + "\n"
        + "➲ /setcaption: " + sc("set your caption") + "\n"
        + "➲ /addchannel: " + sc("add an upload channel") + "\n"
        + "➲ /channels: " + sc("manage your channels") + "\n"
        + "➲ /mystatus: " + sc("your plan and usage") + "\n"
        + "➲ /cmd: " + sc("full command list")
    )
    if owner:
        text += (
            "\n\n<b>" + sc("owner controls") + "</b>\n"
            + "➲ /addpremium: " + sc("give premium") + "\n"
            + "➲ /addfsub: " + sc("force subscribe") + "\n"
            + "➲ /addsite: " + sc("add api site") + "\n"
            + "➲ /botstats: " + sc("bot statistics")
        )
    return text


def about_text():
    return (
        "ⓘ <b>" + sc("about") + "</b>\n"
        + LINE + "\n\n"
        + sc("a fast anime link assistant built for a clean,") + "\n"
        + sc("premium experience.") + "\n\n"
        + "➲ " + sc("download queue with live progress") + "\n"
        + "➲ " + sc("video or document upload") + "\n"
        + "➲ " + sc("custom thumbnail, caption and metadata") + "\n"
        + "➲ " + sc("auto upload to your channel") + "\n"
        + "➲ " + sc("free and premium plans") + "\n\n"
        + "<i>" + sc("powered by") + " @Solurix_bots</i>"
    )


# names kept for older plugin files that import them
START_TEXT = start_text("there")
HELP_TEXT = help_text(False)
ABOUT_TEXT = about_text()


def main_keyboard():
    return Markup([[
        Btn("• " + sc("about"), callback_data="aad:about"),
        Btn(sc("help") + " •", callback_data="hp:main"),
    ]])


def page_keyboard():
    return Markup([[
        Btn("• " + sc("home"), callback_data="aad:home"),
        Btn(sc("close") + " •", callback_data="aad:close"),
    ]])


async def _send_start(message):
    name = message.from_user.first_name if message.from_user else "there"
    text = start_text(name)
    pic = (getattr(Config, "START_PIC", "") or "").strip()
    if pic:
        try:
            await message.reply_photo(
                photo=pic, caption=text, parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
            )
            return
        except Exception as exc:
            LOGGER.warning("START_PIC could not be sent; using text fallback: %s", exc)
    await message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


def register_start_handlers(app):
    @app.on_message(filters.command("start") & filters.private)
    async def start_command(_client, message):
        try:
            await _send_start(message)
        except Exception:
            LOGGER.exception("Failed to send the start screen")
            with suppress(Exception):
                await message.reply_text("Something went wrong. Please try /start again.")

    @app.on_message(filters.command("help") & filters.private)
    async def help_command(_client, message):
        await message.reply_text(
            help_text(is_owner(message.from_user.id)), parse_mode=ParseMode.HTML,
            reply_markup=page_keyboard(), disable_web_page_preview=True,
        )

    @app.on_message(filters.command("about") & filters.private)
    async def about_command(_client, message):
        await message.reply_text(
            about_text(), parse_mode=ParseMode.HTML,
            reply_markup=page_keyboard(), disable_web_page_preview=True,
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
            text, keyboard = help_text(is_owner(query.from_user.id)), page_keyboard()
        elif data == "about":
            text, keyboard = about_text(), page_keyboard()
        else:
            text = start_text(query.from_user.first_name or "there")
            keyboard = main_keyboard()

        try:
            if query.message.photo or query.message.video or query.message.document:
                await query.message.edit_caption(
                    caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard
                )
            else:
                await query.message.edit_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
        except Exception as exc:
            LOGGER.debug("Navigation edit was not applied: %s", exc)
