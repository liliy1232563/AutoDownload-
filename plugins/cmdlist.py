"""/cmd - full command list in small-caps style."""

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton as Btn
from pyrogram.types import InlineKeyboardMarkup as Markup

from plugins.premium import is_owner
from plugins.style import sc

USER_COMMANDS = [
    ("start", "start the bot / check alive"),
    ("help", "how to use the bot"),
    ("about", "about the bot"),
    ("mystatus", "view your plan and usage"),
    ("settings", "upload type, thumbnail, caption, metadata"),
    ("setcaption", "set your custom caption"),
    ("thumb", "view your cover photo"),
    ("delthumb", "remove your cover photo"),
    ("addchannel", "add an upload channel"),
    ("channels", "manage your upload channels"),
    ("metadata", "manage file metadata tags"),
    ("settitle", "set title tag"),
    ("setauthor", "set author tag"),
    ("setartist", "set artist tag"),
    ("setaudio", "set audio track title"),
    ("setsubtitle", "set subtitle track title"),
    ("setvideo", "set video track title"),
    ("setencoded_by", "set encoded by tag"),
    ("setcustom_tag", "set custom tag"),
    ("cmd", "show this command list"),
]

OWNER_COMMANDS = [
    ("addpremium", "give premium to a user (owner)"),
    ("removepremium", "remove premium from a user (owner)"),
    ("premiumlist", "view premium users (owner)"),
    ("botstats", "view bot statistics (owner)"),
    ("addfsub", "add a force-sub channel (owner)"),
    ("delfsub", "remove a force-sub channel (owner)"),
    ("fsubs", "view force-sub channels (owner)"),
    ("addsite", "add an official api site (owner)"),
    ("sites", "view added api sites (owner)"),
    ("removesite", "remove an api site (owner)"),
]


def _lines(items):
    return "\n\n".join(f"/{name} : {sc(desc)}" for name, desc in items)


def build_cmd_text(uid):
    text = f"<b>{sc('commands')}</b>\n\n" + _lines(USER_COMMANDS)
    if is_owner(uid):
        text += f"\n\n━━━━━━━━━━━━━━━\n<b>{sc('owner commands')}</b>\n\n"
        text += _lines(OWNER_COMMANDS)
    return text


def register_cmd_handlers(app):
    @app.on_message(filters.command("cmd") & filters.private)
    async def cmd_list(_client, message):
        await message.reply_text(
            build_cmd_text(message.from_user.id),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=Markup([[Btn("✖ " + sc("close"), callback_data="aad:close")]]),
        )
