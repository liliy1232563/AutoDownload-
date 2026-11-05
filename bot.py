"""Application entry point for Anime Auto Downloader."""

import asyncio
import logging
from contextlib import suppress

from aiohttp import web
from pyrogram import Client, idle

from config import Config
from database.users import init_db
from plugins import register_handlers

SERVICE_NAME = "Anime Auto Downloader"
LOGGER_NAME = "solurix.anime_downloader"


def setup_logging() -> None:
    """Configure consistent, production-friendly application logs."""
    level_name = Config.LOG_LEVEL.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def validate_config() -> None:
    """Fail early when Telegram credentials are missing or invalid."""
    missing = []
    if not Config.BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not Config.API_ID:
        missing.append("API_ID")
    if not Config.API_HASH:
        missing.append("API_HASH")

    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )

    if Config.PORT < 1 or Config.PORT > 65535:
        raise RuntimeError("PORT must be between 1 and 65535")


async def health_handler(_request: web.Request) -> web.Response:
    """Provide a lightweight endpoint for hosting-platform health checks."""
    return web.json_response({"status": "ok", "service": SERVICE_NAME})


async def start_health_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app, access_log=logging.getLogger("aiohttp.access"))
    await runner.setup()

    site = web.TCPSite(runner, host="0.0.0.0", port=Config.PORT)
    try:
        await site.start()
    except Exception:
        await runner.cleanup()
        raise

    logging.getLogger(LOGGER_NAME).info(
        "Health endpoint listening on port %s", Config.PORT
    )
    return runner


async def main() -> None:
    setup_logging()
    log = logging.getLogger(LOGGER_NAME)
    validate_config()

    bot = Client(
        name="anime_auto_downloader",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        in_memory=True,
    )

    health_runner = None
    bot_started = False

    try:
        # Database is optional for local testing, but a configured database
        # must connect successfully before the bot starts accepting requests.
        await init_db()
        register_handlers(bot)
        health_runner = await start_health_server()

        await bot.start()
        bot_started = True
        from plugins.commands_menu import setup_commands
        await setup_commands(bot)
        me = await bot.get_me()
        log.info("Started successfully as @%s", me.username or me.id)
        log.info("Brand: @Solurix_bots")
        await idle()
    except KeyboardInterrupt:
        log.info("Shutdown requested")
    except Exception:
        log.exception("Startup or runtime failure")
        raise
    finally:
        if bot_started:
            with suppress(Exception):
                await bot.stop()
                log.info("Telegram client stopped")

        if health_runner is not None:
            with suppress(Exception):
                await health_runner.cleanup()
                log.info("Health server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
