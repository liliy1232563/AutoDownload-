"""Config-driven adapter for sites that give you an OFFICIAL API.

Sites live in data/sites.json (managed by /addsite) and/or the SITES_JSON
environment variable. Use it only for sites whose owner gave you API access.
"""

import json
import logging
import os
import re
from urllib.parse import quote, urlparse

import aiohttp

from adapters.sources import Resolved, SourceAdapter, register

LOGGER = logging.getLogger("solurix.anime_downloader.apisites")
DATA_DIR = "data"
SITES_FILE = os.path.join(DATA_DIR, "sites.json")


def load_saved_sites():
    try:
        with open(SITES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError):
        return []


def save_sites(sites):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SITES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SITES_FILE)


def load_sites():
    sites = []
    raw = os.getenv("SITES_JSON")
    if raw:
        try:
            env_sites = json.loads(raw)
            if isinstance(env_sites, list):
                sites.extend(env_sites)
        except ValueError:
            LOGGER.warning("SITES_JSON is not valid JSON")
    sites.extend(load_saved_sites())
    return [s for s in sites if isinstance(s, dict) and s.get("domain") and s.get("api_url")]


def find_site(url):
    host = (urlparse(url).hostname or "").lower()
    for site in load_sites():
        domain = str(site["domain"]).lower()
        if host == domain or host.endswith("." + domain):
            return site
    return None


def _dig(data, path):
    """Read nested JSON values with dotted paths, e.g. data.files.0.url"""
    cur = data
    for part in str(path).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
        if cur is None:
            return None
    return cur


class ApiSiteAdapter(SourceAdapter):
    name = "API site"

    def matches(self, url):
        return find_site(url) is not None

    async def resolve(self, url):
        site = find_site(url)
        pattern = site.get("id_regex") or r"([^/?#]+)/?$"
        m = re.search(pattern, url)
        if not m:
            raise RuntimeError("Could not find the video id in this link")
        video_id = m.group(1)

        headers = {}
        key = site.get("api_key") or os.getenv(site.get("api_key_env") or "NO_SUCH_ENV")
        if key:
            header = site.get("key_header") or "Authorization"
            headers[header] = f"{site.get('key_prefix', '')}{key}"

        api_url = site["api_url"].replace("{id}", quote(video_id, safe=""))
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(api_url) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"API replied with status {resp.status}")
                data = await resp.json(content_type=None)

        file_url = _dig(data, site.get("file_key") or "file")
        if not isinstance(file_url, str) or not file_url.startswith(("http://", "https://")):
            raise RuntimeError("API response has no valid file URL")
        title = _dig(data, site.get("title_key") or "title") or f"Video {video_id}"
        return Resolved(file_url, str(title), None, site.get("name") or self.name)


register(ApiSiteAdapter(), first=True)
