"""Anime title search using the public AniList GraphQL API."""
import html
import logging

import aiohttp
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

LOGGER = logging.getLogger("solurix.anime_downloader.search")
ANILIST_URL = "https://graphql.anilist.co"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=8)
MAX_QUERY_LENGTH = 100
MAX_RESULTS = 5

SEARCH_QUERY = """
query ($search: String) {
    Page(perPage: 5) {
        media(search: $search, type: ANIME, isAdult: false) {
            id
            title {
                romaji
                english
            }
            seasonYear
            averageScore
            episodes
            description(asHtml: false)
            siteUrl
        }
    }
}
"""


def _clean(value: object, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return html.escape(text, quote=False)


async def _search_anime(query: str) -> list[dict]:
    payload = {
        "query": SEARCH_QUERY,
        "variables": {"search": query},
    }
    headers = {"User-Agent": "AnimeAutoDownloader/1.0"}

    async with aiohttp.ClientSession(
        timeout=REQUEST_TIMEOUT, headers=headers
    ) as session:
        async with session.post(ANILIST_URL, json=payload) as response:
            if response.status == 429:
                raise RuntimeError(
                    "Search is busy right now. Please try again shortly."
                )
            if response.status != 200:
                raise RuntimeError(
                    "Anime search is temporarily unavailable. Please try again later."
                )
            result = await response.json(content_type=None)

    if not isinstance(result, dict) or result.get("errors"):
        raise RuntimeError("Anime search returned an invalid response.")

    page = result.get("data", {}).get("Page", {})
    media = page.get("media", []) if isinstance(page, dict) else []
    return [item for item in media if isinstance(item, dict)]


def _format_result(item: dict, index: int) -> str:
    titles = item.get("title") or {}
    title = (
        titles.get("english")
        or titles.get("romaji")
        or "Untitled"
    )
    meta = []
    if item.get("seasonYear"):
        meta.append(str(item["seasonYear"]))
    if item.get("averageScore") is not None:
        meta.append(f"Score {item['averageScore'] / 10:.1f}/10")
    if item.get("episodes"):
        meta.append(f"{item['episodes']} eps")

    details = " • ".join(meta) or "Details unavailable"
    synopsis = _clean(item.get("description") or "No synopsis available.", 220)

    return (
        f"<b>{index}. {_clean(title, 120)}</b>\n"
        f"<code>{_clean(details, 80)}</code>\n{synopsis}"
    )


def register_search_handlers(app) -> None:
    """Register /search and /anime title-search commands."""

    @app.on_message(filters.private & filters.command(["search", "anime"]))
    async def search_command(_client, message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.reply_text(
                "<b>𝗔𝗻𝗶𝗺𝗲 𝗦𝗲𝗮𝗿𝗰𝗵</b>\n\n"
                "Use <code>/search anime name</code> to find anime details.\n"
                "Example: <code>/search Naruto</code>\n\n"
                "<i>Powered by @Solurix_bots</i>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return

        query = parts[1].strip()
        if len(query) > MAX_QUERY_LENGTH:
            await message.reply_text(
                f"Please keep your search under {MAX_QUERY_LENGTH} characters."
            )
            return

        status = await message.reply_text("🔎 Searching anime titles…")
        try:
            results = await _search_anime(query)
            if not results:
                await status.edit_text(
                    f"No anime found for <code>{html.escape(query)}</code>. "
                    "Try another title.",
                    parse_mode=ParseMode.HTML,
                )
                return

            blocks = [
                _format_result(item, index)
                for index, item in enumerate(results, start=1)
            ]
            text = (
                f"<b>𝗦𝗲𝗮𝗿𝗰𝗵 𝗥𝗲𝘀𝘂𝗹𝘁𝘀</b>\n"
                f"Query: <code>{html.escape(query)}</code>\n\n"
                + "\n\n".join(blocks)
                + "\n\n<i>Powered by @Solurix_bots</i>"
            )

            buttons = []
            for index, item in enumerate(results, start=1):
                url = item.get("siteUrl")
                if isinstance(url, str) and url.startswith(
                    "https://anilist.co/anime/"
                ):
                    title = (
                        (item.get("title") or {}).get("english")
                        or (item.get("title") or {}).get("romaji")
                        or f"Result {index}"
                    )
                    label = f"{index}. {title}"
                    if len(label) > 32:
                        label = label[:31] + "…"
                    buttons.append([InlineKeyboardButton(label, url=url)])

            markup = InlineKeyboardMarkup(buttons) if buttons else None
            await status.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                disable_web_page_preview=True,
            )

        except (aiohttp.ClientError, TimeoutError) as exc:
            LOGGER.warning("AniList search request failed: %s", exc)
            await status.edit_text(
                "Could not reach anime search right now. Please try again shortly."
            )
        except RuntimeError as exc:
            await status.edit_text(str(exc))
        except Exception:
            LOGGER.exception("Unexpected anime search failure")
            await status.edit_text(
                "Something went wrong during search. Please try again later."
            )
