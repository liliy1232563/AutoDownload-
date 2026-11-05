import asyncio
import html
import json
import logging
import os

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.types import InlineKeyboardButton as Btn
from pyrogram.types import InlineKeyboardMarkup as Markup

LOGGER = logging.getLogger("solurix.anime_downloader.channels")
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "channels.json")
ADMIN_STATES = (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
_lock = asyncio.Lock()


def _read():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def get_user_channels(user_id):
    user = _read().get(str(user_id), {})
    return {"channels": user.get("channels", []), "default": user.get("default")}


def get_default_channel(user_id):
    return get_user_channels(user_id)["default"]


async def _add_channel(user_id, chat_id, title):
    async with _lock:
        data = _read()
        user = data.setdefault(str(user_id), {"channels": [], "default": None})
        if not any(c["id"] == chat_id for c in user["channels"]):
            user["channels"].append({"id": chat_id, "title": title})
        if user.get("default") is None:
            user["default"] = chat_id
        _write(data)


async def _remove_channel(user_id, chat_id):
    async with _lock:
        data = _read()
        user = data.get(str(user_id))
        if not user:
            return
        user["channels"] = [c for c in user["channels"] if c["id"] != chat_id]
        if user.get("default") == chat_id:
            user["default"] = user["channels"][0]["id"] if user["channels"] else None
        _write(data)


async def _set_default(user_id, chat_id):
    async with _lock:
        data = _read()
        user = data.get(str(user_id))
        if user and any(c["id"] == chat_id for c in user["channels"]):
            user["default"] = chat_id
            _write(data)


def build_channels_view(user_id):
    info = get_user_channels(user_id)
    chans = info["channels"]
    if not chans:
        text = (
            "<b>📡 𝗠𝘆 𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀</b>\n━━━━━━━━━━━━━━━\n\n"
            "No channel added yet.\n\n<b>How to add:</b>\n"
            "1️⃣ Add this bot to your channel as <b>Admin</b>\n"
            "2️⃣ Give it <b>Post Messages</b> permission\n"
            "3️⃣ Send:\n<code>/addchannel @yourchannel</code>\nor\n"
            "<code>/addchannel -100123456789</code>"
        )
        return text, Markup([[Btn("⌂ Home", callback_data="aad:home")]])
    text = (
        "<b>📡 𝗠𝘆 𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀</b>\n━━━━━━━━━━━━━━━\n\n"
        "⭐ = default upload channel\n"
        "Tap a channel to make it default, 🗑 to remove.\n\n"
        "<i>Add more: /addchannel @username</i>"
    )
    rows = []
    for c in chans:
        mark = "⭐" if c["id"] == info["default"] else "☆"
        rows.append([
            Btn(f"{mark} {c['title'][:24]}", callback_data=f"ch:def:{c['id']}"),
            Btn("🗑", callback_data=f"ch:del:{c['id']}"),
        ])
    rows.append([Btn("⌂ Home", callback_data="aad:home")])
    return text, Markup(rows)


async def _edit(message, text, markup=None):
    try:
        if message.photo or message.video or message.document:
            await message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)
    except Exception as exc:
        LOGGER.debug("Edit not applied: %s", exc)


def register_channel_handlers(app):
    @app.on_message(filters.command("addchannel") & filters.private)
    async def add_channel_cmd(client, message):
        if len(message.command) < 2:
            text, markup = build_channels_view(message.from_user.id)
            await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            return
        target = message.command[1].strip()
        if target.lstrip("-").isdigit():
            target = int(target)
        status = await message.reply_text("🔍 Checking channel…")
        try:
            chat = await client.get_chat(target)
        except Exception:
            await status.edit_text("❌ Channel not found.\n\nAdd the bot as <b>Admin</b> in the channel first, then try again.", parse_mode=ParseMode.HTML)
            return
        if chat.type not in (ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP):
            await status.edit_text("❌ That is not a channel or group.")
            return
        try:
            bot_member = await client.get_chat_member(chat.id, "me")
            user_member = await client.get_chat_member(chat.id, message.from_user.id)
        except Exception:
            await status.edit_text("❌ I can't verify admin rights.\nMake sure the bot is an <b>Admin</b> in that channel.", parse_mode=ParseMode.HTML)
            return
        if bot_member.status not in ADMIN_STATES:
            await status.edit_text("❌ The bot is not an admin there.\nMake it <b>Admin</b> with <b>Post Messages</b> permission.", parse_mode=ParseMode.HTML)
            return
        privileges = getattr(bot_member, "privileges", None)
        if chat.type == ChatType.CHANNEL and privileges is not None and getattr(privileges, "can_post_messages", True) is False:
            await status.edit_text("❌ The bot needs the <b>Post Messages</b> permission.", parse_mode=ParseMode.HTML)
            return
        if user_member.status not in ADMIN_STATES:
            await status.edit_text("❌ You must be an admin of that channel.")
            return
        title = chat.title or str(chat.id)
        await _add_channel(message.from_user.id, chat.id, title)
        await status.edit_text(f"✅ <b>{html.escape(title)}</b> added!\n\nUse /channels to choose your default upload channel.", parse_mode=ParseMode.HTML)

    @app.on_message(filters.command(["channels", "setchannel"]) & filters.private)
    async def channels_cmd(_client, message):
        text, markup = build_channels_view(message.from_user.id)
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)

    @app.on_callback_query(filters.regex(r"^aad:channels$"))
    async def channels_open(_client, query):
        await query.answer()
        text, markup = build_channels_view(query.from_user.id)
        await _edit(query.message, text, markup)

    @app.on_callback_query(filters.regex(r"^ch:(def|del):(-?\d+)$"))
    async def channels_action(_client, query):
        _, action, raw_id = query.data.split(":")
        chat_id = int(raw_id)
        uid = query.from_user.id
        if action == "def":
            await _set_default(uid, chat_id)
            await query.answer("⭐ Default channel updated")
        else:
            await _remove_channel(uid, chat_id)
            await query.answer("🗑 Channel removed")
        text, markup = build_channels_view(uid)
        await _edit(query.message, text, markup)


_orig_register_channels = register_channel_handlers


def register_channel_handlers(app):
    _orig_register_channels(app)

    @app.on_message(filters.command("delchannel") & filters.private)
    async def del_channel_cmd(client, message):
        uid = message.from_user.id
        chans = get_user_channels(uid)["channels"]

        if len(message.command) < 2:
            text, markup = build_channels_view(uid)
            await message.reply_text(
                "Usage: <code>/delchannel @channel</code> or "
                "<code>/delchannel -100123456789</code>\n\n"
                "Or tap 🗑 below.\n\n" + text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            return

        raw = message.command[1].strip()
        target_id = None
        if raw.lstrip("-").isdigit():
            target_id = int(raw)
        else:
            with suppress(Exception):
                target_id = (await client.get_chat(raw)).id
        if target_id is None:
            for c in chans:
                if c["title"].lower() == raw.lstrip("@").lower():
                    target_id = c["id"]

        if target_id is None or not any(c["id"] == target_id for c in chans):
            await message.reply_text("❌ That channel is not in your list. See /channels.")
            return

        await _remove_channel(uid, target_id)
        await message.reply_text("🗑 Channel removed. See /channels.")
