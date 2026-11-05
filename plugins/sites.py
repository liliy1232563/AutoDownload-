"""Owner-only commands to manage API sites from Telegram."""

import html
import logging
import re
from contextlib import suppress

from pyrogram import filters
from pyrogram.enums import ParseMode

from adapters.apisites import load_saved_sites, save_sites
from config import Config

LOGGER = logging.getLogger("solurix.anime_downloader.sites")

USAGE = (
    "<b>➕ Add a site (official API only)</b>\n\n"
    "Send this, one field per line:\n"
    "<code>/addsite\n"
    "name=My Site\n"
    "domain=mysite.com\n"
    "id_regex=/watch/([^/?#]+)\n"
    "api_url=https://mysite.com/api/video/{id}\n"
    "file_key=data.file\n"
    "title_key=data.title\n"
    "api_key=YOUR_KEY</code>\n\n"
    "Required: name, domain, id_regex, api_url (with {id}).\n"
    "Optional: file_key (default <code>file</code>), title_key (default <code>title</code>), "
    "api_key, key_header (default <code>Authorization</code>), key_prefix (e.g. <code>Bearer </code>).\n\n"
    "Remove: <code>/removesite mysite.com</code>\nList: /sites"
)

ALLOWED = {"name", "domain", "id_regex", "api_url", "file_key", "title_key",
           "api_key", "key_header", "key_prefix", "api_key_env"}


def _is_owner(user_id) -> bool:
    try:
        owner = int(Config.OWNER_ID)
    except (TypeError, ValueError):
        return False
    return owner != 0 and owner == user_id


def _clean_domain(value: str) -> str:
    value = re.sub(r"^https?://", "", value.strip().lower()).split("/")[0]
    return value[4:] if value.startswith("www.") else value


def _parse(text: str) -> dict:
    fields = {}
    for line in text.splitlines()[1:]:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        if key in ALLOWED:
            fields[key] = value.strip("\r") if key == "key_prefix" else value.strip()
    return fields


def _validate(fields: dict):
    for req in ("name", "domain", "id_regex", "api_url"):
        if not fields.get(req):
            return f"Missing field: {req}"
    if not fields["api_url"].startswith("https://"):
        return "api_url must start with https://"
    if "{id}" not in fields["api_url"]:
        return "api_url must contain {id}"
    try:
        compiled = re.compile(fields["id_regex"])
    except re.error:
        return "id_regex is not a valid regex"
    if compiled.groups < 1:
        return "id_regex needs one capture group ( ) around the id"
    if not fields["domain"] or "." not in fields["domain"]:
        return "domain looks invalid"
    return None


def register_site_handlers(app) -> None:
    @app.on_message(filters.command("addsite") & filters.private)
    async def add_site(_client, message):
        if not _is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can add sites.")
            return

        fields = _parse(message.text or "")
        if not fields:
            await message.reply_text(USAGE, parse_mode=ParseMode.HTML)
            return

        fields["domain"] = _clean_domain(fields.get("domain", ""))
        error = _validate(fields)
        had_key = bool(fields.get("api_key"))

        if had_key:
            with suppress(Exception):
                await message.delete()  # hide the API key from the chat

        if error:
            await message.reply_text(f"❌ {html.escape(error)}\n\n/addsite for the format.")
            return

        sites = [s for s in load_saved_sites() if s.get("domain") != fields["domain"]]
        sites.append(fields)
        save_sites(sites)
        await message.reply_text(
            f"✅ <b>{html.escape(fields['name'])}</b> saved "
            f"(<code>{html.escape(fields['domain'])}</code>).\n"
            f"API key: {'set 🔒' if had_key else 'not set'}\n\n"
            "Now send a video link from that site to test.",
            parse_mode=ParseMode.HTML,
        )

    @app.on_message(filters.command("sites") & filters.private)
    async def list_sites(_client, message):
        if not _is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can view sites.")
            return
        sites = load_saved_sites()
        if not sites:
            await message.reply_text("No sites added yet.\n\n/addsite to add one.")
            return
        lines = ["<b>🌐 Your sites</b>\n"]
        for s in sites:
            key = "🔒 key set" if s.get("api_key") else "no key"
            lines.append(
                f"• <b>{html.escape(s.get('name', '?'))}</b> "
                f"<code>{html.escape(s['domain'])}</code> ({key})"
            )
        await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    @app.on_message(filters.command("removesite") & filters.private)
    async def remove_site(_client, message):
        if not _is_owner(message.from_user.id):
            await message.reply_text("⛔ Only the bot owner can remove sites.")
            return
        if len(message.command) < 2:
            await message.reply_text("Usage: /removesite mysite.com")
            return
        domain = _clean_domain(message.command[1])
        sites = load_saved_sites()
        kept = [s for s in sites if s.get("domain") != domain]
        if len(kept) == len(sites):
            await message.reply_text("That site was not found.")
            return
        save_sites(kept)
        await message.reply_text(f"🗑 Removed {html.escape(domain)}.")
