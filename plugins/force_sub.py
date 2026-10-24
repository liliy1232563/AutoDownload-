"""Force-subscription checks for Anime Auto Downloader.

Set FORCE_SUB_CHANNELS to comma-separated Telegram chat IDs in the environment.
The bot must be able to access each channel; for private channels it should be an
administrator with permission to create invite links.
Branding: @Solurix_bots
"""

import logging
from typing import Optional

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.handlers import MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config

LOGGER = logging.getLogger("solurix.anime_downloader.force_sub")
_INVITE_LINK_CACHE: dict[int, str] = {}

PROMPT_TEXT = (
    "<b>🔒 𝗝𝗼𝗶𝗻 𝗥𝗲𝗾𝘂𝗶𝗿𝗲𝗱</b>\n\n"
    "Please join the channel below to use this bot.\n"
    "After joining, tap <b>I've Joined</b> to continue.\n\n"
    "<i>Powered by @Solurix_bots</i>"
)


def _is_member_status(status) -> bool:
    """Treat members and channel administrators as subscribed."""
    return status in {
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    }


async def _invite_link(client, chat_id: int) -> Optional[str]:
    """Get a usable channel link without creating repeated links per message."""
    cached = _INVITE_LINK_CACHE.get(chat_id)
    if cached:
        return cached

    try:
        chat = await client.get_chat(chat_id)
        if getattr(chat, "username", None):
            link = f"https://t.me/{chat.username}"
            _INVITE_LINK_CACHE[chat_id] = link
            return link

        # Private channels may expose their current invite link to administrators.
        link = getattr(chat, "invite_link", None)
        if link:
            _INVITE_LINK_CACHE[chat_id] = link
            return link

        # Creating a link requires the bot to have invite-user permission.
        invite = await client.create_chat_invite_link(
            chat_id=chat_id,
            name="Anime Downloader force-sub",
        )
        link = getattr(invite, "invite_link", None)
        if link:
            _INVITE_LINK_CACHE[chat_id] = link
            return link
    except Exception:
        LOGGER.exception("Could not get an invite link for force-sub channel %s", chat_id)
    return None


async def check_membership(client, user_id: int) -> tuple[bool, list[int]]:
    """Return whether the user joined every configured force-sub channel."""
    missing: list[int] = []
    for chat_id in Config.FORCE_SUB_CHANNELS:
        try:
            member = await client.get_chat_member(chat_id, user_id)
            if not _is_member_status(member.status):
                missing.append(chat_id)
        except Exception as exc:
            # A channel lookup/permission failure must not silently grant access.
            LOGGER.warning(
                "Force-sub check failed for channel=%s user=%s: %s",
                chat_id,
                user_id,
                exc,
            )
            missing.append(chat_id)
    return not missing, missing


async def _build_keyboard(client, missing: list[int]) -> InlineKeyboardMarkup:
    rows = []
    for index, chat_id in enumerate(missing, start=1):
        link = await _invite_link(client, chat_id)
        if link:
            rows.append([InlineKeyboardButton(f"Join Channel {index}", url=link)])

    rows.append([InlineKeyboardButton("I've Joined · Check Again", callback_data="fsub:check")])
    return InlineKeyboardMarkup(rows)


async def _send_prompt(client, message, missing: list[int]) -> None:
    keyboard = await _build_keyboard(client, missing)
    try:
        if Config.FSUB_PIC:
            try:
                await message.reply_photo(
                    photo=Config.FSUB_PIC,
                    caption=PROMPT_TEXT,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                return
            except Exception as exc:
                LOGGER.warning("FSUB_PIC could not be sent; using text: %s", exc)

        await message.reply_text(
            PROMPT_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception:
        LOGGER.exception("Could not send force-sub prompt to user %s", getattr(message.from_user, "id", None))


def register_force_sub_handlers(app) -> None:
    """Register a private-message gate and its membership-check callback.

    The gate is registered in group -1 so it runs before ordinary command handlers.
    StopPropagation prevents commands/download requests from running until joined.
    """
    if not Config.FORCE_SUB_CHANNELS:
        LOGGER.info("Force-sub disabled: FORCE_SUB_CHANNELS is empty")
        return

    @app.on_message(filters.private & filters.incoming, group=-1)
    async def force_sub_gate(client, message):
        user = message.from_user
        if user is None or user.is_bot:
            return

        # The owner is never locked out by their own force-sub configuration.
        if user.id == int(Config.OWNER_ID or 0):
            return

        allowed, missing = await check_membership(client, user.id)
        if allowed:
            return

        await _send_prompt(client, message, missing)
        from pyrogram import StopPropagation
        raise StopPropagation

    @app.on_callback_query(filters.regex(r"^fsub:check$"))
    async def force_sub_check_callback(client, query):
        user = query.from_user
        if user is None:
            await query.answer("Could not identify your account.", show_alert=True)
            return

        allowed, missing = await check_membership(client, user.id)
        if not allowed:
            await query.answer("Please join all required channels first.", show_alert=True)
            try:
                await query.message.edit_reply_markup(
                    reply_markup=await _build_keyboard(client, missing)
                )
            except Exception:
                LOGGER.debug("Could not refresh force-sub buttons", exc_info=True)
            return

        await query.answer("Membership verified. You're all set!", show_alert=True)
        try:
            await query.message.edit_text(
                "<b>✅ 𝗠𝗲𝗺𝗯𝗲𝗿𝘀𝗵𝗶𝗽 𝗩𝗲𝗿𝗶𝗳𝗶𝗲𝗱</b>\n\n"
                "You're good to go. Send your link again to continue.\n\n"
                "<i>Powered by @Solurix_bots</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🏠 Home", callback_data="start:home")]]
                ),
            )
        except Exception:
            LOGGER.exception("Could not update force-sub message for user %s", user.id)
