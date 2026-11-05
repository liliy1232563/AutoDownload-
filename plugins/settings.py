"""Settings hub: upload type, thumbnail, caption and file metadata."""

import html
import json
import os
import re
import shutil
from contextlib import suppress

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton as Btn
from pyrogram.types import InlineKeyboardMarkup as Markup

from config import Config

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "settings.json")
THUMB_DIR = os.path.join("data", "thumbs")
DEFAULTS = {"upload_as": "video", "metadata": True, "template": "",
            "filemeta": False, "tags": {}}
DEFAULT_TEMPLATE = (
    "🎬 <b>{title}</b>\n\n🎞 ǫᴜᴀʟɪᴛʏ: <b>{quality}</b>\n"
    "💾 sɪᴢᴇ: <b>{size}</b>\n\n<i>Powered by @Solurix_bots</i>"
)

TAGS = {
    "title": ("settitle", "Title"),
    "author": ("setauthor", "Author"),
    "artist": ("setartist", "Artist"),
    "audio": ("setaudio", "Audio"),
    "subtitle": ("setsubtitle", "Subtitle"),
    "video": ("setvideo", "Video"),
    "encoded_by": ("setencoded_by", "Encoded By"),
    "custom_tag": ("setcustom_tag", "Custom Tag"),
}
CMD_TO_KEY = {v[0]: k for k, v in TAGS.items()}

_SC = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ",
)


def sc(text):
    return text.lower().translate(_SC)


def _wide(t):
    return f"• {sc(t)} •"


def _left(t):
    return f"• {sc(t)}"


def _right(t):
    return f"{sc(t)} •"


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
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def get_prefs(uid):
    prefs = dict(DEFAULTS)
    prefs.update(_read().get(str(uid), {}))
    prefs["tags"] = dict(prefs.get("tags") or {})
    return prefs


def _update(uid, **changes):
    data = _read()
    data.setdefault(str(uid), {}).update(changes)
    _write(data)


def _human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _dur(seconds):
    s = int(seconds or 0)
    if not s:
        return "—"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def build_caption(prefs, title, label, size, duration, width, height):
    """Caption text ('' when the caption is OFF)."""
    if not prefs.get("metadata", True):
        return ""
    values = {
        "title": html.escape(str(title)[:120]),
        "quality": html.escape(str(label)),
        "size": _human(size),
        "duration": _dur(duration),
        "resolution": f"{width}x{height}" if width and height else "—",
    }
    custom = prefs.get("template")
    tpl = html.escape(custom) if custom else DEFAULT_TEMPLATE
    text = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), tpl)
    return text[:1000]


def _nav():
    return [Btn(_left("close"), callback_data="st:close"),
            Btn(_right("back"), callback_data="st:home")]


def _onoff(flag):
    return "ON ✅" if flag else "OFF ❌"


def _has_thumb(uid):
    return os.path.exists(os.path.join(THUMB_DIR, f"{uid}.jpg"))


def page_home(uid):
    p = get_prefs(uid)
    video = p["upload_as"] == "video"
    text = (
        sc("here is your settings menu:") + "\n\n"
        + sc("customize how your files are uploaded") + " 🫧\n\n"
        + "➲ " + sc("upload as") + ": <b>" + ("Video 🎬" if video else "Document 📄") + "</b>\n"
        + "➲ " + sc("thumbnail") + ": <b>" + ("Set ✅" if _has_thumb(uid) else "Not set ❌") + "</b>\n"
        + "➲ " + sc("caption") + ": <b>" + _onoff(p["metadata"]) + "</b>\n"
        + "➲ " + sc("metadata") + ": <b>" + _onoff(p["filemeta"]) + "</b>\n\n"
        + sc("tap a button below to change it.")
    )
    markup = Markup([
        [Btn(_wide("upload type"), callback_data="st:up")],
        [Btn(_left("thumbnail"), callback_data="st:thumb"),
         Btn(_right("caption"), callback_data="st:cap")],
        [Btn(_left("metadata"), callback_data="st:meta"),
         Btn(_right("close"), callback_data="st:close")],
    ])
    return text, markup


def page_up(uid):
    video = get_prefs(uid)["upload_as"] == "video"
    text = (
        "<u>" + sc("upload type") + "</u>\n\n"
        + "➲ 🎬 " + sc("video") + ": " + sc("plays inside telegram with a seek bar.") + "\n"
        + "➲ 📄 " + sc("document") + ": " + sc("original file, no compression.") + "\n\n"
        + sc("current") + ": <b>" + ("Video 🎬" if video else "Document 📄") + "</b>"
    )
    markup = Markup([
        [Btn(("✅ " if video else "") + "🎬 " + sc("video"), callback_data="st:video"),
         Btn(("" if video else "✅ ") + "📄 " + sc("document"), callback_data="st:document")],
        _nav(),
    ])
    return text, markup


def page_thumb(uid):
    text = (
        "<u>" + sc("to set custom thumbnail") + "</u>\n\n"
        + "➲ " + sc("send any photo to automatically set it as a thumbnail.") + "\n"
        + "➲ /delthumb: " + sc("delete your thumbnail.") + "\n"
        + "➲ /thumb: " + sc("view your current thumbnail.") + "\n\n"
        + sc("note: if no thumbnail is saved, a frame from the video is used.") + "\n\n"
        + sc("current") + ": <b>" + ("Set ✅" if _has_thumb(uid) else "Not set ❌") + "</b>"
    )
    markup = Markup([
        [Btn("🗑 " + sc("delete"), callback_data="st:thumbdel"),
         Btn("👁 " + sc("view"), callback_data="st:thumbview")],
        _nav(),
    ])
    return text, markup


def page_cap(uid):
    p = get_prefs(uid)
    text = (
        "<u>" + sc("caption settings") + "</u>\n\n"
        + "➲ " + sc("caption") + ": <b>" + _onoff(p["metadata"]) + "</b>\n"
        + "➲ " + sc("template") + ": <b>" + ("Custom ✏️" if p["template"] else "Default") + "</b>\n\n"
        + "➲ /setcaption: " + sc("set your caption template.") + "\n"
        + "➲ <code>/setcaption reset</code>: " + sc("back to default.") + "\n\n"
        + sc("placeholders") + ":\n"
        + "<code>{title}</code> <code>{quality}</code> <code>{size}</code> "
        + "<code>{duration}</code> <code>{resolution}</code>"
    )
    markup = Markup([
        [Btn(sc("caption") + ": " + _onoff(p["metadata"]), callback_data="st:capon")],
        [Btn("♻️ " + sc("reset template"), callback_data="st:capreset")],
        _nav(),
    ])
    return text, markup


def page_meta(uid):
    p = get_prefs(uid)
    rows = []
    for key, (cmd, _label) in TAGS.items():
        val = p["tags"].get(key)
        shown = html.escape(val[:26]) if val else "—"
        rows.append("➲ /" + cmd + ": <b>" + shown + "</b>")
    text = (
        "<u>" + sc("managing metadata for your files") + "</u>\n\n"
        + "➲ " + sc("status") + ": <b>" + _onoff(p["filemeta"]) + "</b>\n\n"
        + "\n".join(rows) + "\n\n"
        + sc("example") + ": <code>/settitle {title} - {quality}</code>\n"
        + sc("reset one tag") + ": <code>/settitle reset</code>"
    )
    markup = Markup([
        [Btn(sc("metadata") + ": " + _onoff(p["filemeta"]), callback_data="st:mdon")],
        [Btn("🗑 " + sc("clear all"), callback_data="st:mdclear")],
        _nav(),
    ])
    return text, markup


PAGES = {"home": page_home, "up": page_up, "thumb": page_thumb,
         "cap": page_cap, "meta": page_meta}


async def _show(message, text, markup):
    try:
        if message.photo or message.video or message.document:
            await message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup,
                                    disable_web_page_preview=True)
    except MessageNotModified:
        return
    except Exception:
        with suppress(Exception):
            await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def _send_page(message, uid, page="home"):
    text, markup = PAGES[page](uid)
    pic = (getattr(Config, "START_PIC", "") or "").strip()
    if pic:
        try:
            await message.reply_photo(photo=pic, caption=text, parse_mode=ParseMode.HTML,
                                      reply_markup=markup)
            return
        except Exception:
            pass
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup,
                             disable_web_page_preview=True)


async def _save_thumb(client, uid, photo):
    from plugins.downloader import THUMB_FILTER, _ffmpeg, thumb_path
    if not shutil.which("ffmpeg"):
        return False
    os.makedirs(THUMB_DIR, exist_ok=True)
    raw = None
    try:
        raw = await client.download_media(
            photo.file_id,
            file_name=os.path.abspath(os.path.join(THUMB_DIR, f"{uid}_raw.jpg")),
        )
        return bool(raw) and await _ffmpeg(
            "-i", raw, "-vf", THUMB_FILTER, "-q:v", "5", thumb_path(uid)
        )
    finally:
        if raw:
            with suppress(OSError):
                os.remove(raw)


USAGE_CAPTION = (
    "<b>✏️ Custom caption</b>\n\nSend:\n<code>/setcaption Your text here</code>\n\n"
    "Placeholders:\n<code>{title}</code> <code>{quality}</code> <code>{size}</code> "
    "<code>{duration}</code> <code>{resolution}</code>\n\n"
    "Example:\n<code>/setcaption {title} | {quality} | {size}</code>\n\n"
    "Back to default: <code>/setcaption reset</code>"
)


def register_settings_handlers(app):
    @app.on_message(filters.command("settings") & filters.private)
    async def settings_cmd(_client, message):
        await _send_page(message, message.from_user.id, "home")

    @app.on_message(filters.command("metadata") & filters.private)
    async def metadata_cmd(_client, message):
        await _send_page(message, message.from_user.id, "meta")

    @app.on_callback_query(filters.regex(r"^st:(\w+)$"))
    async def settings_cb(_client, query):
        action = query.data.split(":")[1]
        uid = query.from_user.id
        page = None
        toast = ""

        if action == "close":
            await query.answer("Closed")
            with suppress(Exception):
                await query.message.delete()
            return
        if action == "thumbview":
            path = os.path.join(THUMB_DIR, f"{uid}.jpg")
            if os.path.exists(path):
                await query.answer()
                await query.message.reply_photo(path, caption="🖼 Your current thumbnail")
            else:
                await query.answer("No thumbnail set.", show_alert=True)
            return

        if action in ("video", "document"):
            _update(uid, upload_as=action)
            page, toast = "up", "Saved ✅"
        elif action == "capon":
            _update(uid, metadata=not get_prefs(uid)["metadata"])
            page, toast = "cap", "Saved ✅"
        elif action == "capreset":
            _update(uid, template="")
            page, toast = "cap", "Caption reset ✅"
        elif action == "mdon":
            _update(uid, filemeta=not get_prefs(uid)["filemeta"])
            page, toast = "meta", "Saved ✅"
        elif action == "mdclear":
            _update(uid, tags={})
            page, toast = "meta", "All tags cleared 🗑"
        elif action == "thumbdel":
            path = os.path.join(THUMB_DIR, f"{uid}.jpg")
            if os.path.exists(path):
                os.remove(path)
                toast = "Thumbnail deleted 🗑"
            else:
                toast = "No thumbnail to delete"
            page = "thumb"
        elif action in PAGES:
            page = action
        else:
            await query.answer()
            return

        await query.answer(toast)
        text, markup = PAGES[page](uid)
        await _show(query.message, text, markup)

    @app.on_message(filters.command(list(CMD_TO_KEY)) & filters.private)
    async def set_tag(_client, message):
        cmd = (message.command[0] or "").lower()
        key = CMD_TO_KEY.get(cmd)
        if not key:
            return
        label = TAGS[key][1]
        parts = (message.text or "").split(None, 1)
        if len(parts) < 2:
            await message.reply_text(
                f"Usage: <code>/{cmd} Your {label} here</code>\n"
                f"Remove: <code>/{cmd} reset</code>\n\n"
                "Placeholders: <code>{title}</code> <code>{quality}</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        uid = message.from_user.id
        value = " ".join(parts[1].split())
        tags = get_prefs(uid)["tags"]
        if value.lower() == "reset":
            tags.pop(key, None)
            _update(uid, tags=tags)
            await message.reply_text(f"🗑 {label} removed.")
            return
        if len(value) > 150:
            await message.reply_text("❌ Too long (max 150 characters).")
            return
        tags[key] = value
        _update(uid, tags=tags, filemeta=True)
        await message.reply_text(
            f"✅ <b>{label}</b> saved:\n<code>{html.escape(value)}</code>\n\n"
            "Metadata is ON. See /metadata",
            parse_mode=ParseMode.HTML,
        )

    @app.on_message(filters.command("setcaption") & filters.private)
    async def setcaption_cmd(_client, message):
        parts = (message.text or "").split(None, 1)
        if len(parts) < 2:
            await message.reply_text(USAGE_CAPTION, parse_mode=ParseMode.HTML)
            return
        arg = parts[1].strip()
        uid = message.from_user.id
        if arg.lower() == "reset":
            _update(uid, template="")
            await message.reply_text("✅ Caption reset to default.")
            return
        if len(arg) > 500:
            await message.reply_text("❌ Caption is too long (max 500 characters).")
            return
        _update(uid, template=arg)
        preview = build_caption(get_prefs(uid), "Sample Episode 01", "720p",
                                150 * 1024 * 1024, 1420, 1280, 720)
        await message.reply_text("✅ Caption saved. Preview:\n\n" + preview,
                                 parse_mode=ParseMode.HTML)

    @app.on_message(filters.private & filters.photo & ~filters.command(["setthumb"]))
    async def auto_thumb(client, message):
        ok = await _save_thumb(client, message.from_user.id, message.photo)
        if ok:
            await message.reply_text(
                "✅ Thumbnail saved. It will be used on all your uploads.\n\n"
                "/settings → Thumbnail to manage it."
            )
        else:
            await message.reply_text("❌ Could not save that photo. Try a different one.")
