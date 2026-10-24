"""Owner/admin commands for Anime Auto Downloader.

Commands:
  /addadmin <user_id>  - Owner only; grant admin access.
  /deladmin <user_id>  - Owner only; revoke admin access.
  /adminlist           - Owner/admin; show current admins.

Persistent admin records require DATABASE_URL (MongoDB).
Branding: @Solurix_bots
"""

import logging
import re
from contextlib import suppress

from pyrogram import filters
from pyrogram.enums import ParseMode

from config import Config
from database.users import get_admins_collection

LOGGER = logging.getLogger("solurix.anime_downloader.admin")
USER_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
DENIED_TEXT = (
    "<b>⛔ 𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱</b>\n\n"
    "You are not my kuchupuchuuu 😞\n"
    "<i>This command is only for my admins.</i>"
)


def _owner_id() -> int:
    return int(Config.OWNER_ID or 0)


def _is_owner(user_id: int) -> bool:
    return user_id > 0 and user_id == _owner_id()


async def _is_admin(user_id: int) -> bool:
    if _is_owner(user_id):
        return True
    collection = get_admins_collection()
    if collection is None:
        return False
    try:
        return await collection.find_one({"user_id": user_id}, {"_id": 1}) is not None
    except Exception:
        LOGGER.exception("Could not verify admin status for user_id=%s", user_id)
        return False


async def _deny(message) -> None:
    await message.reply_text(DENIED_TEXT, parse_mode=ParseMode.HTML)


def _parse_target(message) -> int | None:
    parts = (message.text or "").split()
    if len(parts) != 2 or not USER_ID_RE.fullmatch(parts[1]):
        return None
    try:
        target = int(parts[1])
    except ValueError:
        return None
    return target if target > 0 else None


def register_admin_handlers(app) -> None:
    """Register owner/admin commands with server-side authorization checks."""

    @app.on_message(filters.private & filters.command("addadmin"))
    async def add_admin_command(_client, message):
        sender = message.from_user
        if sender is None or not _is_owner(sender.id):
            await _deny(message)
            return

        target_id = _parse_target(message)
        if target_id is None:
            await message.reply_text(
                "Usage: <code>/addadmin user_id</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        if target_id == _owner_id():
            await message.reply_text("Owner already has full access.")
            return

        collection = get_admins_collection()
        if collection is None:
            await message.reply_text(
                "Admin storage is unavailable. Set DATABASE_URL and restart the bot."
            )
            return
        try:
            result = await collection.update_one(
                {"user_id": target_id},
                {"$setOnInsert": {"user_id": target_id, "added_by": sender.id}},
                upsert=True,
            )
            if result.upserted_id is None:
                await message.reply_text(f"User <code>{target_id}</code> is already an admin.", parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(f"✅ Added <code>{target_id}</code> to the admin list.", parse_mode=ParseMode.HTML)
        except Exception:
            LOGGER.exception("Failed to add admin %s", target_id)
            await message.reply_text("Could not update the admin list. Please try again later.")

    @app.on_message(filters.private & filters.command("deladmin"))
    async def delete_admin_command(_client, message):
        sender = message.from_user
        if sender is None or not _is_owner(sender.id):
            await _deny(message)
            return

        target_id = _parse_target(message)
        if target_id is None:
            await message.reply_text(
                "Usage: <code>/deladmin user_id</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        if target_id == _owner_id():
            await message.reply_text("The owner cannot be removed from admin access.")
            return

        collection = get_admins_collection()
        if collection is None:
            await message.reply_text(
                "Admin storage is unavailable. Set DATABASE_URL and restart the bot."
            )
            return
        try:
            result = await collection.delete_one({"user_id": target_id})
            if result.deleted_count:
                await message.reply_text(f"Removed <code>{target_id}</code> from the admin list.", parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(f"<code>{target_id}</code> is not in the admin list.", parse_mode=ParseMode.HTML)
        except Exception:
            LOGGER.exception("Failed to remove admin %s", target_id)
            await message.reply_text("Could not update the admin list. Please try again later.")

    @app.on_message(filters.private & filters.command("adminlist"))
    async def admin_list_command(_client, message):
        sender = message.from_user
        if sender is None or not await _is_admin(sender.id):
            await _deny(message)
            return

        collection = get_admins_collection()
        if collection is None:
            await message.reply_text("Admin storage is unavailable. Set DATABASE_URL and restart the bot.")
            return
        try:
            admin_ids = [int(item["user_id"]) async for item in collection.find({}, {"user_id": 1}).sort("user_id", 1)]
            if _owner_id() > 0:
                admin_ids = [_owner_id()] + [item for item in admin_ids if item != _owner_id()]
            if not admin_ids:
                await message.reply_text("No admins are configured yet.")
                return
            body = "\n".join(f"• <code>{user_id}</code>" for user_id in admin_ids)
            await message.reply_text(
                f"<b>𝗔𝗱𝗺𝗶𝗻 𝗟𝗶𝘀𝘁</b>\n\n{body}\n\n<i>Powered by @Solurix_bots</i>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            LOGGER.exception("Failed to list admins")
            await message.reply_text("Could not load the admin list. Please try again later.")
