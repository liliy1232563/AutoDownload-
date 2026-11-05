"""Help centre: category buttons, each opens a short command page."""

import logging

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton as Btn
from pyrogram.types import InlineKeyboardMarkup as Markup

from config import Config
from plugins.premium import is_owner
from plugins.style import sc

LOGGER = logging.getLogger("solurix.anime_downloader.helpmenu")

# key: (button label, emoji, page title, rows, footer)
PAGES = {
    "dl": ("download", "📥", "download", [
        ("send a link", "start a download"),
        ("quality buttons", "360p up to best"),
        ("all quality 💎", "one file for every quality"),
    ], "🆓 free: 3 per day, up to 480p\n💎 premium: unlimited, up to 1080p"),
    "set": ("settings", "⚙️", "settings", [
        ("/settings", "open the settings menu"),
        ("/setcaption", "set your own caption"),
        ("/thumb", "view your cover photo"),
        ("/delthumb", "remove your cover photo"),
        ("send a photo", "saves it as your cover photo"),
    ], ""),
    "chn": ("channels", "📡", "channels", [
        ("/addchannel", "add your upload channel"),
        ("/channels", "pick the default channel"),
    ], "make the bot admin in your channel first."),
    "meta": ("metadata", "🏷", "metadata", [
        ("/metadata", "see and manage your tags"),
        ("/settitle", "set title"),
        ("/setauthor", "set author"),
        ("/setartist", "set artist"),
        ("/setaudio", "set audio track title"),
        ("/setsubtitle", "set subtitle track title"),
        ("/setvideo", "set video track title"),
        ("/setencoded_by", "set encoded by"),
        ("/setcustom_tag", "set custom tag"),
    ], "add reset after a command to remove that tag."),
    "acc": ("account", "👤", "account", [
        ("/mystatus", "your plan and usage"),
        ("/start", "start the bot"),
        ("/about", "about the bot"),
        ("/cmd", "full command list"),
    ], ""),
    "owner": ("owner", "👑", "owner controls", [
        ("/addpremium", "give premium"),
        ("/removepremium", "remove premium"),
        ("/premiumlist", "premium users"),
        ("/botstats", "bot statistics"),
        ("/addfsub", "add force subscribe"),
        ("/delfsub", "remove force subscribe"),
        ("/fsubs", "force subscribe list"),
        ("/addsite", "add an official api site"),
        ("/sites", "list api sites"),
        ("/removesite", "remove an api site"),
    ], ""),
}

ORDER = ["dl", "set", "chn", "meta", "acc", "owner"]


def main_text():
    return (
        "✦ <b>" + sc("command centre") + "</b> ✦\n\n"
        "<blockquote>" + sc("explore all commands below.") + "\n"
        + sc("all commands start with /") + "</blockquote>\n\n"
        "<i>" + sc("send a link, pick a quality and get your file in your channel.") + "</i>"
    )


def page_text(key):
    _label, emoji, title, rows, footer = PAGES[key]
    lines = []
    for cmd, desc in rows:
        c = cmd if cmd.startswith("/") else sc(cmd)
        lines.append(f"▸ {c} — {sc(desc)}")
    text = f"{emoji} <b>{sc(title)}</b>\n\n<blockquote>" + "\n".join(lines) + "</blockquote>"
    if footer:
        text += "\n\n<i>" + sc(footer) + "</i>"
    return text


def build(key, uid):
    if key == "main":
        keys = [k for k in ORDER if k != "owner" or is_owner(uid)]
        buttons = [Btn(sc(PAGES[k][0]), callback_data=f"hp:{k}") for k in keys]
        rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
        rows.append([Btn("• " + sc("back") + " •", callback_data="aad:home")])
        return main_text(), Markup(rows)
    rows = [[Btn("• " + sc("back") + " •", callback_data="hp:main")]]
    return page_text(key), Markup(rows)


async def _show(message, text, markup):
    try:
        if message.photo or message.video or message.document:
            await message.edit_caption(
                caption=text, parse_mode=ParseMode.HTML, reply_markup=markup
            )
        else:
            await message.edit_text(
                text, parse_mode=ParseMode.HTML, reply_markup=markup,
                disable_web_page_preview=True,
            )
    except MessageNotModified:
        return
    except Exception as exc:
        LOGGER.debug("Help edit not applied: %s", exc)


def register_help_handlers(app):
    @app.on_message(filters.command("help") & filters.private, group=-1)
    async def help_cmd(_client, message):
        text, markup = build("main", message.from_user.id)
        pic = (getattr(Config, "START_PIC", "") or "").strip()
        sent = False
        if pic:
            try:
                await message.reply_photo(
                    photo=pic, caption=text, parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                )
                sent = True
            except Exception as exc:
                LOGGER.warning("Help picture failed: %s", exc)
        if not sent:
            await message.reply_text(
                text, parse_mode=ParseMode.HTML, reply_markup=markup,
                disable_web_page_preview=True,
            )
        message.stop_propagation()

    @app.on_callback_query(filters.regex(r"^hp:(\w+)$"))
    async def help_cb(_client, query):
        key = query.data.split(":")[1]
        uid = query.from_user.id
        if key != "main" and key not in PAGES:
            await query.answer()
            return
        if key == "owner" and not is_owner(uid):
            await query.answer("Owner only.", show_alert=True)
            return
        await query.answer()
        text, markup = build(key, uid)
        await _show(query.message, text, markup)
