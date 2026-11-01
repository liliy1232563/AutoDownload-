"""URL validation and SSRF protection for Anime Auto Downloader.

Only public HTTP(S) URLs are accepted. DNS answers are checked so callers can
reject local/private network destinations before making an outbound request.
The downloader should still pin the validated DNS answers when connecting to
avoid DNS-rebinding between validation and the actual request.

Branding: @Solurix_bots
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class UnsafeURL(ValueError):
    """Raised when a URL is malformed or points to an unsafe destination."""


@dataclass(frozen=True, slots=True)
class ValidatedURL:
    """A normalized URL and the public IP addresses resolved for its host."""

    url: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_PORTS = {80, 443}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".invalid", ".example")


def _is_public_address(value: str) -> bool:
    """Return True only for globally routable unicast IP addresses."""
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_global and not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _parse_url(url: str) -> tuple[str, str, int, str, str]:
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURL("Please send a valid URL.")

    candidate = url.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in candidate):
        raise UnsafeURL("The URL contains invalid control characters.")

    try:
        parts = urlsplit(candidate)
        scheme = parts.scheme.lower()
        hostname = (parts.hostname or "").rstrip(".").lower()
        port = parts.port
    except ValueError as exc:
        raise UnsafeURL("The URL format is invalid.") from exc

    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURL("Only HTTP and HTTPS links are supported.")
    if not hostname or parts.username is not None or parts.password is not None:
        raise UnsafeURL("The URL must contain a valid host and no embedded credentials.")
    if hostname == "localhost" or hostname.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeURL("Local or internal network addresses are not allowed.")

    effective_port = port or (443 if scheme == "https" else 80)
    if effective_port not in _ALLOWED_PORTS:
        raise UnsafeURL("Custom network ports are not supported.")

    # Reject IP literals unless they are globally routable.
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not _is_public_address(hostname):
            raise UnsafeURL("Private or non-public IP addresses are not allowed.")

    # Drop fragments; they are never sent to the HTTP server.
    normalized = urlunsplit((scheme, parts.netloc, parts.path or "/", parts.query, ""))
    return normalized, scheme, effective_port, hostname, parts.netloc


async def validate_url(url: str, *, dns_timeout: float = 8.0) -> ValidatedURL:
    """Validate an HTTP(S) URL and resolve its host to public IP addresses.

    Raises:
        UnsafeURL: If parsing, scheme, port, hostname, DNS, or IP checks fail.
    """
    normalized, scheme, port, hostname, _netloc = _parse_url(url)

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await asyncio.wait_for(
                loop.getaddrinfo(
                    hostname,
                    port,
                    family=socket.AF_UNSPEC,
                    type=socket.SOCK_STREAM,
                    proto=socket.IPPROTO_TCP,
                ),
                timeout=dns_timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise UnsafeURL("Could not safely resolve the link's host.") from exc
        addresses = tuple(dict.fromkeys(info[4][0].split("%", 1)[0] for info in infos))
    else:
        addresses = (str(literal),)

    if not addresses:
        raise UnsafeURL("The link's host did not resolve.")
    if any(not _is_public_address(address) for address in addresses):
        raise UnsafeURL("The link resolves to a private or non-public network address.")

    return ValidatedURL(
        url=normalized,
        scheme=scheme,
        hostname=hostname,
        port=port,
        addresses=addresses,
    )


def validate_url_syntax(url: str) -> str:
    """Perform synchronous syntax checks without DNS resolution.

    Use ``await validate_url(...)`` before making network requests. This helper
    is intended for quick input checks only and does not establish host safety.
    """
    normalized, _scheme, _port, _hostname, _netloc = _parse_url(url)
    return normalized
