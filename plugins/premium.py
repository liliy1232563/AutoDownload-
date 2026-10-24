"""Premium membership commands for Anime Auto Downloader.

Commands:
  /premium                 - View premium information
  /myplan                  - Check your current membership
  /addpremium <id> <days>  - Grant/extend premium access
  /remove_premium <id>     - Remove premium access
  /premium_users           - List active premium members

Premium records are stored in MongoDB and use UTC expiry timestamps.
Branding: @Solurix_bots
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database.users import get_database

LOGGER = logging.getLogger("solurix.anime_downloader.premium")
USER_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
MAX_PREMIUM_DAYS = 3650

DENIED_TEXT = (
    "<b>⛔ 𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱</b>\n\n"
    "You are not my kuchupuchuuu 😞\n"
    "<i>This command is only for my admins.</i>"
)

PREMIUM_TEXT = (
    "<b>👑 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗠𝗲𝗺𝗯𝗲𝗿𝘀𝗵𝗶𝗽</b>\n\n"
    "Premium access is managed by the bot team.\n"
    "Use /myplan to check your current status.\n\n"
    "<i>Powered by @Solurix_bots</i>"
)


def _now_utc_naive() -> datetime:
    """MongoDB stores naive UTC datetimes by default; use the same convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_owner(user_id: int) -> bool:
    return user_id > 0 and user_id == int(Config.OWNER_ID or 0)


async def _is_admin(user_id: int) -> bool:
    if _is_owner(user_id):
        return True
    database = get_database()
    if database is None:
        return False
    try:
        return await database.admins.find_one({"user_id": user_id}, {"_id": 1}) is not None
    except Exception:
        LOGGER.exception("Could not verify admin status for user_id=%s", user_id)
        return False


async def _deny(message) -> None:
    await message.reply_text(DENIED_TEXT, parse_mode=ParseMode.HTML)


def _parse_user_id(value: str) -> int | None:
    if not USER_ID_RE.fullmatch(value):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _premium_collection():
    database = get_database()
    return database.premium_users if database is not None else None


async def _get_active_record(user_id: int):
    collection = _premium_collection()
    if collection is None:
        return None, "unavailable"
    try:
        record = await collection.find_one({"user_id": user_id})
    except Exception:
        LOGGER.exception("Could not read premium record for user_id=%s", user_id)
        return None, "error"
    if not record:
        return None, "inactive"
    expires_at = record.get("expires_at")
    if not isinstance(expires_at, datetime):
        return None, "inactive"
    # Motor's default codec returns naive UTC datetimes.
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    if expires_at <= _now_utc_naive():
        return record, "expired"
    return record, "active"


def _format_date(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime("%d %b %Y, %H:%M UTC")


def _premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("↻ Check My Plan", callback_data="premium:myplan")]]
    )


def register_premium_handlers(app) -> None:
    """Register premium information, membership checks and management commands."""

    @app.on_message(filters.private & filters.command(["premium", "premiuminfo"]))
    async def premium_info_command(_client, message):
        try:
            if Config.PREMIUM_PIC:
                try:
                    await message.reply_photo(
                        Config.PREMIUM_PIC,
                        caption=PREMIUM_TEXT,
                        parse_mode=ParseMode.HTML,
                        reply_markup=_premium_keyboard(),
                    )
                    return
                except Exception as exc:
                    LOGGER.warning("PREMIUM_PIC could not be sent; using text: %s", exc)
            await message.reply_text(
                PREMIUM_TEXT,
                parse_mode=ParseMode.HTML,
                reply_markup=_premium_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            LOGGER.exception("Failed to send premium information")
            await message.reply_text("Could not open premium information right now. Please try again.")

    @app.on_message(filters.private & filters.command("myplan"))
    async def my_plan_command(_client, message):
        sender = message.from_user
        if sender is None:
            await message.reply_text("Could not identify your Telegram account.")
            return
        record, status = await _get_active_record(sender.id)
        if status == "unavailable":
            await message.reply_text("Premium storage is unavailable. Please contact the bot owner.")
        elif status == "error":
            await message.reply_text("Could not check your plan right now. Please try again later.")
        elif status == "active" and record:
            expires_at = record["expires_at"]
            await message.reply_text(
                "<b>👑 𝗬𝗼𝘂𝗿 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗣𝗹𝗮𝗻</b>\n\n"
                f"Status: <b>Active</b>\nExpires: <code>{_format_date(expires_at)}</code>\n\n"
                "<i>Powered by @Solurix_bots</i>",
                parse_mode=ParseMode.HTML,
            )
        elif status == "expired" and record:
            await message.reply_text(
                "<b>𝗬𝗼𝘂𝗿 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗣𝗹𝗮𝗻</b>\n\n"
                f"Status: Expired\nExpired on: <code>{_format_date(record['expires_at'])}</code>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text(
                "You don't have an active premium plan yet.\nUse /premium for details."
            )

    @app.on_message(filters.private & filters.command("addpremium"))
    async def add_premium_command(_client, message):
        sender = message.from_user
        if sender is None or not await _is_admin(sender.id):
            await _deny(message)
            return
        parts = (message.text or "").split()
        if len(parts) != 3:
            await message.reply_text(
                "Usage: <code>/addpremium user_id days</code>\nExample: <code>/addpremium 123456789 30</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        target_id = _parse_user_id(parts[1])
        try:
            days = int(parts[2])
        except ValueError:
            days = 0
        if target_id is None or days < 1 or days > MAX_PREMIUM_DAYS:
            await message.reply_text(f"Enter a valid user ID and a duration from 1 to {MAX_PREMIUM_DAYS} days.")
            return
        collection = _premium_collection()
        if collection is None:
            await message.reply_text("Premium storage is unavailable. Set DATABASE_URL and restart the bot.")
            return
        try:
            existing = await collection.find_one({"user_id": target_id})
            now = _now_utc_naive()
            current_expiry = existing.get("expires_at") if existing else None
            if isinstance(current_expiry, datetime):
                if current_expiry.tzinfo is not None:
                    current_expiry = current_expiry.astimezone(timezone.utc).replace(tzinfo=None)
                base = max(now, current_expiry)
            else:
                base = now
            expires_at = base + timedelta(days=days)
            await collection.update_one(
                {"user_id": target_id},
                {"$set": {
                    "user_id": target_id,
                    "expires_at": expires_at,
                    "updated_at": now,
                    "updated_by": sender.id,
                }, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            await message.reply_text(
                "<b>✅ Premium Updated</b>\n\n"
                f"User: <code>{target_id}</code>\nAdded: <b>{days} days</b>\n"
                f"Expires: <code>{_format_date(expires_at)}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            LOGGER.exception("Failed to grant premium to user_id=%s", target_id)
            await message.reply_text("Could not update premium access. Please try again later.")

    @app.on_message(filters.private & filters.command("remove_premium"))
    async def remove_premium_command(_client, message):
        sender = message.from_user
        if sender is None or not await _is_admin(sender.id):
            await _deny(message)
            return
        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.reply_text(
                "Usage: <code>/remove_premium user_id</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        target_id = _parse_user_id(parts[1])
        if target_id is None:
            await message.reply_text("Please provide a valid numeric Telegram user ID.")
            return
        collection = _premium_collection()
        if collection is None:
            await message.reply_text("Premium storage is unavailable. Set DATABASE_URL and restart the bot.")
            return
        try:
            result = await collection.delete_one({"user_id": target_id})
            if result.deleted_count:
                await message.reply_text(f"Removed premium access for <code>{target_id}</code>.", parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(f"User <code>{target_id}</code> has no premium record.", parse_mode=ParseMode.HTML)
        except Exception:
            LOGGER.exception("Failed to remove premium for user_id=%s", target_id)
            await message.reply_text("Could not remove premium access. Please try again later.")

    @app.on_message(filters.private & filters.command("premium_users"))
    async def premium_users_command(_client, message):
        sender = message.from_user
        if sender is None or not await _is_admin(sender.id):
            await _deny(message)
            return
        collection = _premium_collection()
        if collection is None:
            await message.reply_text("Premium storage is unavailable. Set DATABASE_URL and restart the bot.")
            return
        try:
            now = _now_utc_naive()
            records = [record async for record in collection.find(
                {"expires_at": {"$gt": now}},
                {"user_id": 1, "expires_at": 1},
            ).sort("expires_at", 1).limit(50)]
            if not records:
                await message.reply_text("No active premium members found.")
                return
            lines = [
                f"• <code>{int(record['user_id'])}</code> — {_format_date(record['expires_at'])}"
                for record in records
                if "user_id" in record and isinstance(record.get("expires_at"), datetime)
            ]
            await message.reply_text(
                "<b>👑 𝗔𝗰𝘁𝗶𝘃𝗲 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗨𝘀𝗲𝗿𝘀</b>\n\n"
                + ("\n".join(lines) if lines else "No active premium members found.")
                + "\n\n<i>Showing up to 50 members.</i>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            LOGGER.exception("Failed to list premium members")
            await message.reply_text("Could not load premium users right now. Please try again later.")

    @app.on_callback_query(filters.regex(r"^premium:myplan$"))
    async def premium_plan_callback(_client, query):
        await query.answer()
        sender = query.from_user
        record, status = await _get_active_record(sender.id)
        if status == "unavailable":
            text = "Premium storage is unavailable. Please contact the bot owner."
        elif status == "error":
            text = "Could not check your plan right now. Please try again later."
        elif status == "active" and record:
            text = f"👑 Premium is active until {_format_date(record['expires_at'])} (UTC)."
        elif status == "expired" and record:
            text = f"Your premium plan expired on {_format_date(record['expires_at'])} (UTC)."
        else:
            text = "You don't have an active premium plan yet."
        try:
            await query.message.reply_text(text)
        except Exception:
            LOGGER.exception("Failed to reply to premium callback")
