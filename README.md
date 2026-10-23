# Anime Auto Downloader

A Telegram bot project designed to process supported anime and video links, with plans for direct delivery and automatic channel uploads. Built with a clean structure so it can be tested on Render and later moved to a VPS.

**Maintained with ❤️ by [@Solurix_bots](https://t.me/Solurix_bots)**

## Features

- Simple `/start`, `/help`, and `/about` commands
- MongoDB support for basic user records and statistics
- Health endpoint for hosting checks (`/health`)
- Configurable images for bot pages
- Initial URL validation and automated tests
- Environment-based configuration for easier deployment

> **Project status:** This is the Phase 1 foundation. The download engine, website-specific adapters, upload workflow, force-subscription checks, job queue, and premium enforcement are not implemented yet. A valid-looking URL does not guarantee that its source is supported.

## Requirements

- Python 3.10 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Telegram `API_ID` and `API_HASH`
- MongoDB connection string (`DATABASE_URL`)

## Setup

```bash
git clone <your-repository-url>
cd <your-project-folder>
cp .env.example .env
pip install -r requirements.txt
```

Add your values to `.env`, then start the bot:

```bash
python bot.py
```

Run the tests with:

```bash
python -m unittest discover -s tests
```

## Configuration

Set these values in `.env` or your hosting provider's environment settings:

- `BOT_TOKEN`, `API_ID`, `API_HASH` — Telegram credentials
- `OWNER_ID` — Telegram user ID of the bot owner
- `DATABASE_URL` — MongoDB connection string
- `START_PIC`, `HELP_PIC`, `ABOUT_PIC` — optional image file IDs or public HTTPS image URLs
- `FSUB_PIC`, `PREMIUM_PIC`, `DOWNLOAD_PIC` — reserved for upcoming features

Keep credentials private. Never upload your `.env` file or expose bot tokens in public repositories.

## Deploying on Render

1. Push the project to your GitHub repository.
2. Create a Render Web Service or use the included `render.yaml` blueprint.
3. Set the build command to `pip install -r requirements.txt` and the start command to `python bot.py`.
4. Add the required environment variables and deploy.
5. Check the service's `/health` endpoint.

Render's free services can sleep and have storage and resource limits. Large files and long-running download jobs should be tested carefully; a VPS and persistent storage may be more suitable for production use.

## Responsible Use

Only process media you have permission to download. This project is not intended to bypass DRM, login requirements, or other access controls. Website support depends on each source and its technical restrictions.

## Support

For project updates and support, visit [@Solurix_bots](https://t.me/Solurix_bots).
