"""Publish the command list to Telegram so the Menu button shows."""

import logging

from pyrogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from config import Config
from plugins.cmdlist import OWNER_COMMANDS, USER_COMMANDS

LOGGER = logging.getLogger("solurix.anime_downloader.menu")


def _cmds(items):
    return [BotCommand(name, desc[:250]) for name, desc in items]


async def setup_commands(bot):
    user = _cmds(USER_COMMANDS)
    try:
        await bot.set_bot_commands(user)
        await bot.set_bot_commands(user, scope=BotCommandScopeAllPrivateChats())
    except Exception:
        LOGGER.exception("Could not set the bot command menu")
        return
    try:
        owner_id = int(Config.OWNER_ID or 0)
        if owner_id:
            await bot.set_bot_commands(
                user + _cmds(OWNER_COMMANDS), scope=BotCommandScopeChat(owner_id)
            )
    except Exception as exc:
        LOGGER.warning("Owner command menu not set: %s", exc)
