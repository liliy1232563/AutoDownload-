
"""Plugin registration for Anime Auto Downloader."""

from plugins.start import register_start_handlers
from plugins.downloader import register_downloader_handlers
from plugins.search import register_search_handlers
from plugins.admin import register_admin_handlers
from plugins.premium import register_premium_handlers
from plugins.force_sub import register_force_sub_handlers
from plugins.callbacks import register_callback_handlers


def register_handlers(app) -> None:
    """Register all Anime Auto Downloader handlers."""

    # Membership protection
    register_force_sub_handlers(app)

    # Core bot handlers
    register_start_handlers(app)
    register_search_handlers(app)
    register_downloader_handlers(app)

    # User management
    register_admin_handlers(app)
    register_premium_handlers(app)

    # Shared navigation callbacks
    register_callback_handlers(app)


__all__ = ["register_handlers"]
