"""Free / Premium plans, daily limits and owner admin commands.

Storage: data/users.json. Settings via environment variables:
FREE_DAILY_LIMIT (default 3), FREE_MAX_QUALITY (default 480),
PREMIUM_CONTACT (default @Solurix_bots).
"""

import html
import json
import logging
import os
import time
from contextlib import suppress
from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.enums import ParseMode

from config import Config

LOGGER = logging.getLogger("solurix.anime_downloader.premium")
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "users.json")

FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "3"))
FREE_MAX_QUALITY = int(os.getenv("FREE_MAX_QUALITY", "480"))
PREMIUM_CONTACT = os.getenv("PREMIUM_CONTACT", "@Solurix_bots")


def _read():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def _write(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DATA_FILE)


def _data():
    d = _read()
    d.setdefault("premium", {})
    d.setdefault("usage", {})
    return d


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _owner_id():
    try:
        return int(Config.OWNER_ID)
    except (TypeError, ValueError):
        return 0


def is_owner(uid):
    return _owner_id() != 0 and uid == _owner_id()


def premium_expiry(uid):
    """None = not premium, 0 = lifetime, otherwise expiry timestamp."""
    if is_owner(uid):
        return 0
    exp = _data()["premium"].get(str(uid))
    if exp is None:
        return None
    if exp == 0 or exp > time.time():
        return exp
    return None


def is_premium(uid):
    return premium_expiry(uid) is not None


def used_today(uid):
    u = _data()["usage"].get(str(uid))
    return u["count"] if u and u.get("day") == _today() else 0


def record_download(uid):
    d = _data()
    today = _today()
    u = d["usage"].get(str(uid))
    if not u or u.get("day") != today:
        u = {"day": today, "count": 0}
    u["count"] += 1
    d["usage"][str(uid)] = u
    _write(d)


def check_limits(uid, choice):
    """Return (allowed, message)."""
    if is_premium(uid):
        return True, ""
    quality = 9999 if choice == "best" else int(choice)
    if quality > FREE_MAX_QUALITY:
        return False, (
            f"🔒 This quality is for Premium users.\n"
            f"Free plan: up to {FREE_MAX_QUALITY}p.\nUpgrade: {PREMIUM_CONTACT}"
        )
    if used_today(uid) >= FREE_DAILY_LIMIT:
        return False, (
            f"⏳ Daily free limit reached ({FREE_DAILY_LIMIT}/day).\n"
            f"Resets at 00:00 UTC.\nUpgrade: {PREMIUM_CONTACT}"
        )
    return True, ""


def _fmt_exp(exp):
    if exp == 0:
        return "Lifetime"
    return datetime.fromtimestamp(exp, timezone.utc).strftime("%d %b %Y")


def register_premium_handlers(app):
    @app.on_message(filters.command("mystatus") & filters.private)
    async def my_status(_client, message):
        uid = message.from_user.id
        exp = premium_expiry(uid)
        if exp is not None:
            text = (
                "<b>💎 𝗣𝗥𝗘𝗠𝗜𝗨𝗠</b>\n━━━━━━━━━━━━━━━\n\n"
                f"📅 Valid until: <b>{_fmt_exp(exp)}</b>\n"
                "📥 Downloads: <b>Unlimited</b>\n"
                "🎞 Quality: <b>Up to 1080p / Best</b>\n"
                f"📊 Today: {used_today(uid)} downloads"
            )
        else:
            left = max(FREE_DAILY_LIMIT - used_today(uid), 0)
            text = (
                "<b>🆓 𝗙𝗥𝗘𝗘 𝗣𝗟𝗔𝗡</b>\n━━━━━━━━━━━━━━━\n\n"
                f"📥 Downloads left today: <b>{left}/{FREE_DAILY_LIMIT}</b>\n"
                f"🎞 Max quality: <b>{FREE_MAX_QUALITY}p</b>\n\n"
                f"💎 Upgrade to Premium for unlimited downloads\n"
                f"and up to 1080p: {html.escape(PREMIUM_CONTACT)}"
            )
        await message.reply_text(text, parse_mode=ParseMode.HTML)

    @app.on_message(filters.command("addpremium") & filters.private)
    async def add_premium(client, message):
        if not is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can use this.")
            return
        args = message.command[1:]
        if not args or not args[0].lstrip("-").isdigit():
            await message.reply_text(
                "Usage: <code>/addpremium USER_ID [DAYS]</code>\n"
                "Default 30 days. Use 0 for lifetime.",
                parse_mode=ParseMode.HTML,
            )
            return
        target = int(args[0])
        days = 30
        if len(args) > 1:
            if not args[1].isdigit():
                await message.reply_text("DAYS must be a number.")
                return
            days = int(args[1])
        exp = 0 if days == 0 else time.time() + days * 86400
        d = _data()
        d["premium"][str(target)] = exp
        _write(d)
        await message.reply_text(
            f"✅ Premium given to <code>{target}</code> ({'lifetime' if days == 0 else f'{days} days'}).",
            parse_mode=ParseMode.HTML,
        )
        with suppress(Exception):
            await client.send_message(
                target,
                f"💎 <b>You are now Premium!</b>\nValid until: <b>{_fmt_exp(exp)}</b>\n\nCheck /mystatus",
                parse_mode=ParseMode.HTML,
            )

    @app.on_message(filters.command("removepremium") & filters.private)
    async def remove_premium(_client, message):
        if not is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can use this.")
            return
        args = message.command[1:]
        if not args or not args[0].lstrip("-").isdigit():
            await message.reply_text("Usage: /removepremium USER_ID")
            return
        d = _data()
        if d["premium"].pop(args[0], None) is None:
            await message.reply_text("That user is not premium.")
            return
        _write(d)
        await message.reply_text(f"🗑 Premium removed from {html.escape(args[0])}.")

    @app.on_message(filters.command("premiumlist") & filters.private)
    async def premium_list(_client, message):
        if not is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can use this.")
            return
        now = time.time()
        rows = [
            f"• <code>{uid}</code> — {_fmt_exp(exp)}"
            for uid, exp in _data()["premium"].items()
            if exp == 0 or exp > now
        ]
        text = "<b>💎 Premium users</b>\n\n" + "\n".join(rows) if rows else "No premium users yet."
        await message.reply_text(text, parse_mode=ParseMode.HTML)

    @app.on_message(filters.command("botstats") & filters.private)
    async def bot_stats(_client, message):
        if not is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can use this.")
            return
        d = _data()
        now, today = time.time(), _today()
        premium = sum(1 for e in d["premium"].values() if e == 0 or e > now)
        downloads = sum(u["count"] for u in d["usage"].values() if u.get("day") == today)
        await message.reply_text(
            "<b>📊 Bot stats</b>\n\n"
            f"👥 Users who downloaded: <b>{len(d['usage'])}</b>\n"
            f"💎 Active premium: <b>{premium}</b>\n"
            f"📥 Downloads today: <b>{downloads}</b>",
            parse_mode=ParseMode.HTML,
        )
