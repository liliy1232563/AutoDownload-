"""Write metadata tags into the media file with ffmpeg."""

import asyncio
import logging
import os
import re
import shutil
from contextlib import suppress

LOGGER = logging.getLogger("solurix.anime_downloader.filemeta")


def _clean(value, values):
    value = re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), value)
    return " ".join(value.split())[:200]


async def _run(args):
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-loglevel", "error", *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=900)
        return proc.returncode == 0
    except Exception:
        if proc is not None and proc.returncode is None:
            with suppress(Exception):
                proc.kill()
        return False


async def apply_metadata(path, tags, values):
    """Return the path of the tagged file (or the original if tagging fails)."""
    if not tags or not shutil.which("ffmpeg"):
        return path
    clean = {k: _clean(v, values) for k, v in tags.items() if v}
    clean = {k: v for k, v in clean.items() if v}
    if not clean:
        return path

    base, ext = os.path.splitext(path)
    out = f"{base}_meta{ext}"

    global_meta = []
    for key, field in (("title", "title"), ("author", "author"), ("artist", "artist"),
                       ("encoded_by", "encoded_by"), ("custom_tag", "comment")):
        if key in clean:
            global_meta += ["-metadata", f"{field}={clean[key]}"]

    stream_meta = []
    for key, spec in (("audio", "a"), ("subtitle", "s"), ("video", "v")):
        if key in clean:
            stream_meta += [
                f"-metadata:s:{spec}", f"title={clean[key]}",
                f"-metadata:s:{spec}", f"handler_name={clean[key]}",
            ]

    extra = ["-movflags", "+faststart"] if ext.lower() in (".mp4", ".m4v", ".mov") else []
    attempts = (
        ["-map", "0:v?", "-map", "0:a?", "-map", "0:s?"],
        ["-map", "0:v?", "-map", "0:a?"],
    )
    for maps in attempts:
        args = ["-i", path, *maps, "-c", "copy", "-map_metadata", "0",
                *global_meta, *stream_meta, *extra, out]
        ok = await _run(args)
        if ok and os.path.exists(out) and os.path.getsize(out) > 0:
            with suppress(OSError):
                os.remove(path)
            return out
        with suppress(OSError):
            os.remove(out)
    LOGGER.warning("Metadata could not be written; sending the original file")
    return path
