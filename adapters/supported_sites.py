"""Host matching adapter for explicitly supported public anime/media sites.

This module only identifies URLs and delegates extraction to registered
site-specific handlers. It does not bypass DRM, authentication, paywalls,
or other access restrictions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urlsplit


class UnsupportedSiteError(ValueError):
    """Raised when no registered handler supports the supplied URL."""


@dataclass(frozen=True, slots=True)
class SiteMatch:
    name: str
    host: str
    handler: Callable[[str], Awaitable[object]]


class SupportedSites:
    """Register site handlers and resolve URLs to their matching handler."""

    def __init__(self) -> None:
        self._handlers: dict[str, SiteMatch] = {}

    @staticmethod
    def _normalize_host(host: str) -> str:
        value = host.strip().lower().rstrip(".")
        if not value or "/" in value or ":" in value:
            raise ValueError("Provide a hostname only, e.g. example.com")
        return value.removeprefix("www.")

    def register(
        self,
        name: str,
        hosts: list[str] | tuple[str, ...],
        handler: Callable[[str], Awaitable[object]],
    ) -> None:
        if not name.strip():
            raise ValueError("Site name cannot be empty")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if not hosts:
            raise ValueError("At least one hostname is required")

        normalized = [self._normalize_host(host) for host in hosts]
        duplicates = [host for host in normalized if host in self._handlers]
        if duplicates:
            raise ValueError(f"Hosts already registered: {', '.join(duplicates)}")

        for host in normalized:
            self._handlers[host] = SiteMatch(name=name.strip(), host=host, handler=handler)

    def unregister(self, host: str) -> bool:
        return self._handlers.pop(self._normalize_host(host), None) is not None

    def match(self, url: str) -> SiteMatch | None:
        try:
            parsed = urlsplit(url.strip())
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                return None
            host = parsed.hostname.lower().rstrip(".").removeprefix("www.")
        except (TypeError, ValueError):
            return None

        # Exact host or a true subdomain; avoids unsafe suffix matches.
        candidates = [host]
        parts = host.split(".")
        candidates.extend(".".join(parts[index:]) for index in range(1, len(parts) - 1))
        for candidate in candidates:
            found = self._handlers.get(candidate)
            if found is not None:
                return found
        return None

    async def extract(self, url: str) -> object:
        found = self.match(url)
        if found is None:
            raise UnsupportedSiteError("This website is not currently supported.")
        return await found.handler(url)

    def supported_hosts(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))


supported_sites = SupportedSites()
