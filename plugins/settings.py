"""Per-user upload settings: Video/Document, metadata caption, custom template."""

import html
import json
import os
import re
from contextlib import suppress

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton as Btn
from pyrogram.types import InlineKeyboardMarkup as Markup

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "settings.json")
DEFAULTS = {"upload_as": "video", "metadata": True, "template": ""}
DEFAULT_TEMPLATE = (
    "🎬 <b>{title}</b>\n\n🎞 Quality: <b>{quality}</b>\n"
    "💾 Size: <b>{size}</b>\n\n<i>Powered by @Solurix_bots</i>"
)


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
    """Return the caption text ('' when metadata is OFF)."""
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


def _view(uid):
    p = get_prefs(uid)
    video = p["upload_as"] == "video"
    template = "Custom ✏️" if p.get("template") else "Default"
    text = (
        "<b>⚙️ 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦</b>\n━━━━━━━━━━━━━━━\n\n"
        f"📤 Upload as: <b>{'Video 🎬' if video else 'Document 📄'}</b>\n"
        f"🧾 Metadata caption: <b>{'ON' if p['metadata'] else 'OFF'}</b>\n"
        f"✏️ Caption template: <b>{template}</b>\n\n"
        "<i>Edit caption: /setcaption</i>"
    )
    markup = Markup([
        [
            Btn(("✅ " if video else "") + "🎬 Video", callback_data="st:video"),
            Btn(("" if video else "✅ ") + "📄 Document", callback_data="st:document"),
        ],
        [Btn(f"🧾 Metadata: {'ON ✅' if p['metadata'] else 'OFF ❌'}", callback_data="st:md")],
        [Btn("✖ Close", callback_data="st:close")],
    ])
    return text, markup


USAGE = (
    "<b>✏️ Custom caption</b>\n\n"
    "Send:\n<code>/setcaption Your text here</code>\n\n"
    "Placeholders:\n"
    "<code>{title}</code> <code>{quality}</code> <code>{size}</code> "
    "<code>{duration}</code> <code>{resolution}</code>\n\n"
    "Example:\n<code>/setcaption {title} | {quality} | {size}</code>\n\n"
    "Back to default: <code>/setcaption reset</code>"
)


def register_settings_handlers(app):
    @app.on_message(filters.command("settings") & filters.private)
    async def settings_cmd(_client, message):
        text, markup = _view(message.from_user.id)
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

    @app.on_callback_query(filters.regex(r"^st:(video|document|md|close)$"))
    async def settings_cb(_client, query):
        action = query.data.split(":")[1]
        uid = query.from_user.id
        if action == "close":
            await query.answer("Closed")
            with suppress(Exception):
                await query.message.delete()
            return
        if action in ("video", "document"):
            _update(uid, upload_as=action)
        else:
            _update(uid, metadata=not get_prefs(uid)["metadata"])
        await query.answer("Saved ✅")
        text, markup = _view(uid)
        with suppress(Exception):
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

    @app.on_message(filters.command("setcaption") & filters.private)
    async def setcaption_cmd(_client, message):
        parts = (message.text or "").split(None, 1)
        if len(parts) < 2:
            await message.reply_text(USAGE, parse_mode=ParseMode.HTML)
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
        preview = build_caption(
            get_prefs(uid), "Sample Episode 01", "720p", 150 * 1024 * 1024, 1420, 1280, 720
        )
        await message.reply_text(
            "✅ Caption saved. Preview:\n\n" + preview, parse_mode=ParseMode.HTML
        )
