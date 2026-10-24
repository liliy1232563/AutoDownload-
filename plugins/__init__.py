"""Plugin registration for Anime Auto Downloader."""

from plugins.start import register_start_handlers


def register_handlers(app) -> None:
    """Register all bot command and callback handlers."""
    register_start_handlers(app)


__all__ = ["register_handlers"]
