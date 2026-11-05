"""Force-subscribe with temporary join links (expire in 10 minutes).

Storage: data/fsub.json. Owner commands: /addfsub, /delfsub, /fsubs.
The bot must be an ADMIN (with Invite Users permission) in each channel.
"""

import html
import json
import logging
import os
import time
from contextlib import suppress
from datetime import datetime

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton as Btn
from pyrogram.types import InlineKeyboardMarkup as Markup

from plugins.premium import is_owner

LOGGER = logging.getLogger("solurix.anime_downloader.fsub")
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "fsub.json")
NOT_JOINED = (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
ADMIN_STATES = (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)

LINK_TTL = 10 * 60  # join links expire after 10 minutes
LINK_CACHE = {}  # (user_id, chat_id) -> (url, expires_at)


def load_channels():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError):
        return []


def save_channels(channels):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


async def _temp_link(client, ch, uid):
    """One-person join link that expires in 10 minutes (cached per user)."""
    key = (uid, ch["id"])
    now = time.time()
    cached = LINK_CACHE.get(key)
    if cached and cached[1] - now > 60:
        return cached[0]
    try:
        invite = await client.create_chat_invite_link(
            ch["id"],
            name=f"fsub-{uid}"[:32],
            expire_date=datetime.fromtimestamp(now + LINK_TTL),
            member_limit=1,
        )
        if len(LINK_CACHE) > 5000:
            LINK_CACHE.clear()
        LINK_CACHE[key] = (invite.invite_link, now + LINK_TTL)
        return invite.invite_link
    except Exception as exc:
        LOGGER.warning("Could not create temp link for %s: %s", ch["id"], exc)
        return ch.get("link")  # fallback: saved permanent link


async def missing_channels(client, uid, links=True):
    """Channels the user has NOT joined (owner is never blocked).

    With links=True each returned channel carries a fresh 10-minute link.
    """
    if is_owner(uid):
        return []
    missing = []
    for ch in load_channels():
        try:
            member = await client.get_chat_member(ch["id"], uid)
            joined = member.status not in NOT_JOINED
        except UserNotParticipant:
            joined = False
        except Exception as exc:
            # Can't verify (bot removed etc.): don't lock users out.
            LOGGER.warning("fsub check failed for %s: %s", ch.get("id"), exc)
            continue
        if joined:
            continue
        item = dict(ch)
        if links:
            item["link"] = await _temp_link(client, ch, uid)
        missing.append(item)
    return missing


def gate_text():
    return (
        "🔒 <b>𝗝𝗢𝗜𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗</b>\n━━━━━━━━━━━━━━━\n\n"
        "To use this bot, please join the channel(s) below,\n"
        "then tap <b>✅ I've Joined</b>.\n\n"
        "⏳ <i>Join links are valid for 10 minutes.\n"
        "Expired? Tap 🔄 New Link.</i>"
    )


def join_markup(missing):
    rows = [
        [Btn(f"📢 Join {c['title'][:24]}", url=c["link"])]
        for c in missing
        if c.get("link")
    ]
    rows.append(
        [
            Btn("🔄 New Link", callback_data="fs:refresh"),
            Btn("✅ I've Joined", callback_data="fs:check"),
        ]
    )
    return Markup(rows)


def register_fsub_handlers(app):
    @app.on_callback_query(filters.regex(r"^fs:(check|refresh)$"))
    async def fs_buttons(client, query):
        uid = query.from_user.id
        action = query.data.split(":")[1]

        if action == "refresh":
            for key in [k for k in LINK_CACHE if k[0] == uid]:
                LINK_CACHE.pop(key, None)

        missing = await missing_channels(client, uid, links=(action == "refresh"))

        if not missing:
            await query.answer("Verified ✅")
            with suppress(Exception):
                await query.message.edit_text(
                    "✅ <b>Verified!</b>\n\nNow send your link.",
                    parse_mode=ParseMode.HTML,
                )
            return

        if action == "check":
            await query.answer("You haven't joined all channels yet.", show_alert=True)
            return

        await query.answer("New links created ✅")
        with suppress(Exception):
            await query.message.edit_text(
                gate_text(), parse_mode=ParseMode.HTML, reply_markup=join_markup(missing)
            )

    @app.on_message(filters.command("addfsub") & filters.private)
    async def add_fsub(client, message):
        if not is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can use this.")
            return
        if len(message.command) < 2:
            await message.reply_text(
                "Usage: <code>/addfsub @channel</code> or <code>/addfsub -100123456789</code>\n\n"
                "The bot must be an <b>Admin</b> with the <b>Invite Users</b> permission.",
                parse_mode=ParseMode.HTML,
            )
            return
        target = message.command[1].strip()
        if target.lstrip("-").isdigit():
            target = int(target)
        status = await message.reply_text("🔍 Checking channel…")
        try:
            chat = await client.get_chat(target)
            me = await client.get_chat_member(chat.id, "me")
        except Exception:
            await status.edit_text("❌ Channel not found, or the bot is not in it.\nAdd the bot as Admin first.")
            return
        if me.status not in ADMIN_STATES:
            await status.edit_text("❌ The bot must be an <b>Admin</b> there to verify members.", parse_mode=ParseMode.HTML)
            return

        # Can the bot create expiring links?
        can_expire = True
        try:
            test = await client.create_chat_invite_link(
                chat.id, name="fsub-test", expire_date=datetime.fromtimestamp(time.time() + 60)
            )
            with suppress(Exception):
                await client.revoke_chat_invite_link(chat.id, test.invite_link)
        except Exception:
            can_expire = False

        link = f"https://t.me/{chat.username}" if chat.username else None
        if not link:
            try:
                link = await client.export_chat_invite_link(chat.id)
            except Exception:
                await status.edit_text(
                    "❌ Private channel: give the bot the <b>Invite Users</b> admin permission.",
                    parse_mode=ParseMode.HTML,
                )
                return

        title = chat.title or str(chat.id)
        channels = [c for c in load_channels() if c["id"] != chat.id]
        channels.append({"id": chat.id, "title": title, "link": link})
        save_channels(channels)

        note = (
            "\n⏳ Join links will expire in 10 minutes."
            if can_expire
            else "\n⚠️ The bot lacks <b>Invite Users</b> permission, so links will NOT expire. Give that permission and run this command again."
        )
        await status.edit_text(
            f"✅ Force-subscribe added: <b>{html.escape(title)}</b>{note}",
            parse_mode=ParseMode.HTML,
        )

    @app.on_message(filters.command("delfsub") & filters.private)
    async def del_fsub(_client, message):
        if not is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can use this.")
            return
        if len(message.command) < 2:
            await message.reply_text("Usage: /delfsub CHANNEL_ID  (see /fsubs)")
            return
        key = message.command[1].strip().lstrip("@").lower()
        channels = load_channels()
        kept = [
            c for c in channels
            if str(c["id"]) != key and not c["link"].lower().endswith("/" + key)
        ]
        if len(kept) == len(channels):
            await message.reply_text("That channel was not found. Check /fsubs.")
            return
        save_channels(kept)
        await message.reply_text("🗑 Removed from force-subscribe.")

    @app.on_message(filters.command("fsubs") & filters.private)
    async def list_fsubs(_client, message):
        if not is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can use this.")
            return
        channels = load_channels()
        if not channels:
            await message.reply_text("No force-subscribe channels.\n\n/addfsub @channel to add one.")
            return
        lines = ["<b>🔒 Force-subscribe channels</b>\n"]
        for c in channels:
            lines.append(f"• <b>{html.escape(c['title'])}</b> <code>{c['id']}</code>")
        await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
