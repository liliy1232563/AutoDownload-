import asyncio
import glob
import html
import logging
import os
import re
import shutil
import time
import uuid
from contextlib import suppress

import yt_dlp
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton as Btn
from pyrogram.types import InlineKeyboardMarkup as Markup

from plugins.channels import get_default_channel

LOGGER = logging.getLogger("solurix.anime_downloader.downloader")
URL_RE = re.compile(r"https?://\S+")
DOWNLOAD_DIR = "downloads"
MAX_UPLOAD = 2 * 1024**3
MAX_PENDING = 200
MAX_PARALLEL = 2
PENDING = {}
ACTIVE = set()
TASKS = set()
SLOTS = asyncio.Semaphore(MAX_PARALLEL)


def esc(t):
    return html.escape(str(t))


def human(n):
    if not n:
        return "0 B"
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_time(s):
    if s is None:
        return "—"
    s = int(s)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h}h {m}m {sec}s" if h else f"{m}m {sec}s"


def bar(p):
    p = max(0.0, min(100.0, p))
    f = int(p // 10)
    return "█" * f + "░" * (10 - f)


def progress_text(stage, title, pct, done, total, speed=None, eta=None):
    return (
        f"<b>{stage}</b>\n━━━━━━━━━━━━━━━\n🎬 {esc(title[:60])}\n\n"
        f"[{bar(pct)}] <b>{pct:.1f}%</b>\n"
        f"📦 {human(done)} / {human(total) if total else '?'}\n"
        f"⚡ {human(speed) + '/s' if speed else '—'}\n"
        f"⏳ ETA: {fmt_time(eta)}"
    )


async def safe_edit(message, text, markup=None):
    with suppress(Exception):
        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)


def _extract(url):
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


async def _download(status, url, quality, workdir, title):
    loop = asyncio.get_running_loop()
    state = {"t": 0.0}
    has_ffmpeg = shutil.which("ffmpeg") is not None
    if quality == "best":
        fmt = "bv*+ba/b" if has_ffmpeg else "b"
    elif has_ffmpeg:
        fmt = f"bv*[height<={quality}]+ba/b[height<={quality}]/b"
    else:
        fmt = f"b[height<={quality}]/b"

    def hook(d):
        if d.get("status") != "downloading":
            return
        now = time.monotonic()
        if now - state["t"] < 3:
            return
        state["t"] = now
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0
        pct = done * 100 / total if total else 0
        text = progress_text("⬇️ Downloading", title, pct, done, total, d.get("speed"), d.get("eta"))
        asyncio.run_coroutine_threadsafe(safe_edit(status, text), loop)

    opts = {
        "format": fmt,
        "outtmpl": os.path.join(workdir, "%(title).70s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "merge_output_format": "mp4",
        "restrictfilenames": True,
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "fragment_retries": 5,
    }

    def run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    info = await asyncio.to_thread(run)
    files = [f for f in glob.glob(os.path.join(workdir, "*")) if not f.endswith((".part", ".ytdl", ".json", ".temp"))]
    if not files:
        raise RuntimeError("No file was produced")
    return max(files, key=os.path.getsize), info


async def _upload(client, status, path, info, title, quality, target):
    size = os.path.getsize(path)
    if size > MAX_UPLOAD:
        raise RuntimeError("File is larger than Telegram's 2 GB limit")
    height = info.get("height")
    label = f"{height}p" if height else quality
    caption = (
        f"🎬 <b>{esc(title)}</b>\n\n🎞 Quality: <b>{esc(label)}</b>\n"
        f"💾 Size: <b>{human(size)}</b>\n\n<i>Powered by @Solurix_bots</i>"
    )
    started = time.monotonic()
    last = {"t": 0.0}

    async def up_progress(current, total):
        now = time.monotonic()
        if now - last["t"] < 3 and current != total:
            return
        last["t"] = now
        speed = current / max(now - started, 0.1)
        eta = (total - current) / speed if speed else None
        pct = current * 100 / total if total else 0
        await safe_edit(status, progress_text("⬆️ Uploading", title, pct, current, total, speed, eta))

    if path.lower().endswith(".mp4"):
        await client.send_video(
            chat_id=target, video=path, caption=caption, parse_mode=ParseMode.HTML,
            duration=int(info.get("duration") or 0), width=int(info.get("width") or 0),
            height=int(height or 0), supports_streaming=True, progress=up_progress,
        )
    else:
        await client.send_document(
            chat_id=target, document=path, caption=caption,
            parse_mode=ParseMode.HTML, progress=up_progress,
        )


async def _run_job(client, status, job, quality, uid):
    workdir = os.path.join(DOWNLOAD_DIR, uuid.uuid4().hex[:8])
    os.makedirs(workdir, exist_ok=True)
    title = job["title"]
    chat_id = status.chat.id
    target = get_default_channel(uid) or chat_id
    try:
        await safe_edit(status, "⏳ <b>Queued…</b>\nWaiting for a free slot.")
        async with SLOTS:
            await safe_edit(status, "🚀 <b>Starting download…</b>")
            path, info = await _download(status, job["url"], quality, workdir, title)
            try:
                await _upload(client, status, path, info, title, quality, target)
            except Exception:
                LOGGER.exception("Upload failed")
                hint = "Make sure the bot is still an admin in your channel." if target != chat_id else "Please try again."
                await safe_edit(status, f"❌ <b>Upload failed.</b>\n{hint}")
                return
        where = "your channel" if target != chat_id else "this chat"
        await safe_edit(status, f"✅ <b>Done!</b>\n\n🎬 {esc(title[:60])}\n📤 Sent to {where}.")
    except Exception:
        LOGGER.exception("Download failed")
        await safe_edit(status, "❌ <b>Download failed.</b>\nThe link may be unsupported, private, or expired.")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        ACTIVE.discard(uid)


def quality_keyboard(token):
    return Markup([
        [Btn("📱 360p", callback_data=f"dl:{token}:360"), Btn("📺 480p", callback_data=f"dl:{token}:480")],
        [Btn("🖥 720p", callback_data=f"dl:{token}:720"), Btn("🎥 1080p", callback_data=f"dl:{token}:1080")],
        [Btn("👑 Best Quality", callback_data=f"dl:{token}:best")],
        [Btn("✖ Cancel", callback_data=f"dl:{token}:x")],
    ])


def register_download_handlers(app):
    @app.on_message(
        filters.private & filters.text
        & ~filters.command(["start", "help", "about", "addchannel", "channels", "setchannel"])
        & filters.regex(URL_RE.pattern)
    )
    async def on_link(_client, message):
        url = URL_RE.search(message.text).group(0)
        wait = await message.reply_text("🔎 <b>Checking link…</b>", parse_mode=ParseMode.HTML)
        try:
            info = await asyncio.to_thread(_extract, url)
        except Exception as exc:
            LOGGER.exception("Link check failed")
            reason = esc(str(exc).replace("ERROR: ", "")[:200])
            await safe_edit(wait, f"❌ <b>Link not supported or not accessible.</b>\n\n<code>{reason}</code>")
            return
        if len(PENDING) >= MAX_PENDING:
            PENDING.pop(next(iter(PENDING)))
        token = uuid.uuid4().hex[:8]
        title = info.get("title") or "Video"
        PENDING[token] = {"url": url, "uid": message.from_user.id, "title": title}
        text = (
            "<b>🎬 𝗟𝗶𝗻𝗸 𝗥𝗲𝗮𝗱𝘆</b>\n━━━━━━━━━━━━━━━\n\n"
            f"📝 <b>{esc(title[:80])}</b>\n"
            f"⏱ Duration: {fmt_time(info.get('duration'))}\n\n👇 <b>Select quality:</b>"
        )
        await safe_edit(wait, text, quality_keyboard(token))

    @app.on_callback_query(filters.regex(r"^dl:([0-9a-f]{8}):(360|480|720|1080|best|x)$"))
    async def on_quality(client, query):
        _, token, choice = query.data.split(":")
        job = PENDING.get(token)
        if not job or job["uid"] != query.from_user.id:
            await query.answer("This request expired. Send the link again.", show_alert=True)
            return
        if choice == "x":
            PENDING.pop(token, None)
            await query.answer("Cancelled")
            await safe_edit(query.message, "✖ <b>Cancelled.</b>")
            return
        uid = query.from_user.id
        if uid in ACTIVE:
            await query.answer("One download at a time. Please wait.", show_alert=True)
            return
        PENDING.pop(token, None)
        ACTIVE.add(uid)
        await query.answer("Added to queue ✅")
        task = asyncio.create_task(_run_job(client, query.message, job, choice, uid))
        TASKS.add(task)
        task.add_done_callback(TASKS.discard)


def register_downloader_handlers(app):
    from plugins.channels import register_channel_handlers
    register_channel_handlers(app)
    register_download_handlers(app)
