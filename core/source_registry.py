"""Adapter registry for supported download sources.

Adapters are registered explicitly by the application. A website is not
considered supported merely because it has a URL; each adapter must implement
the agreed interface and respect the source site's access rules.

Branding: @Solurix_bots
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit


class UnsupportedSource(ValueError):
    """Raised when no registered adapter supports a URL."""


@runtime_checkable
class SourceAdapter(Protocol):
    """Minimal interface expected from a source adapter."""

    name: str
    hosts: tuple[str, ...]

    async def extract(self, url: str) -> dict[str, Any]:
        """Return source metadata and a permitted media URL."""


@dataclass(frozen=True, slots=True)
class AdapterMatch:
    """A registered adapter and the host rule that matched the URL."""

    adapter: SourceAdapter
    matched_host: str


class SourceRegistry:
    """Explicit, deterministic registry for supported website adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    @staticmethod
    def _normalize_host(host: str) -> str:
        value = host.strip().lower().rstrip(".")
        if not value or "/" in value or ":" in value or "@" in value:
            raise ValueError(f"Invalid adapter hostname: {host!r}")
        return value.encode("idna").decode("ascii")

    @staticmethod
    def _host_from_url(url: str) -> str:
        try:
            parts = urlsplit(url)
            host = parts.hostname
        except (TypeError, ValueError) as exc:
            raise UnsupportedSource("Invalid source URL.") from exc
        if parts.scheme.lower() not in {"http", "https"} or not host:
            raise UnsupportedSource("Only HTTP and HTTPS source URLs are supported.")
        return host.rstrip(".").lower().encode("idna").decode("ascii")

    def register(self, adapter: SourceAdapter) -> None:
        """Register an adapter; duplicate host ownership is rejected."""
        name = getattr(adapter, "name", None)
        hosts = getattr(adapter, "hosts", None)
        extract = getattr(adapter, "extract", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Adapter must define a non-empty name.")
        if not isinstance(hosts, (tuple, list)) or not hosts:
            raise ValueError(f"Adapter {name!r} must define one or more hosts.")
        if not callable(extract):
            raise TypeError(f"Adapter {name!r} must implement async extract(url).")

        normalized_hosts = [self._normalize_host(host) for host in hosts]
        if len(set(normalized_hosts)) != len(normalized_hosts):
            raise ValueError(f"Adapter {name!r} contains duplicate host entries.")
        conflicts = [host for host in normalized_hosts if host in self._adapters]
        if conflicts:
            raise ValueError("A source adapter is already registered for: " + ", ".join(conflicts))
        for host in normalized_hosts:
            self._adapters[host] = adapter

    def unregister(self, adapter_name: str) -> int:
        """Remove every host entry belonging to an adapter name."""
        keys = [host for host, adapter in self._adapters.items()
                if getattr(adapter, "name", None) == adapter_name]
        for host in keys:
            del self._adapters[host]
        return len(keys)

    def find(self, url: str) -> AdapterMatch | None:
        """Find the most specific registered host, including subdomains."""
        host = self._host_from_url(url)
        candidates = [registered for registered in self._adapters
                      if host == registered or host.endswith("." + registered)]
        if not candidates:
            return None
        matched = max(candidates, key=len)
        return AdapterMatch(self._adapters[matched], matched)

    def get(self, url: str) -> SourceAdapter:
        """Return the adapter for URL or raise UnsupportedSource."""
        match = self.find(url)
        if match is None:
            raise UnsupportedSource("This website is not currently supported.")
        return match.adapter

    def is_supported(self, url: str) -> bool:
        """Return whether a registered website adapter matches the URL."""
        try:
            return self.find(url) is not None
        except (UnsupportedSource, UnicodeError):
            return False

    def list_sources(self) -> list[dict[str, str]]:
        """Return unique registered adapters for an admin/help display."""
        unique: dict[int, SourceAdapter] = {}
        for adapter in self._adapters.values():
            unique[id(adapter)] = adapter
        return [{"name": str(adapter.name), "hosts": ", ".join(sorted(set(adapter.hosts)))}
                for adapter in sorted(unique.values(), key=lambda item: item.name.lower())]


# Shared registry. Register adapters during application startup.
source_registry = SourceRegistry()
