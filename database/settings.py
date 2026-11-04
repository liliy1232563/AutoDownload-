# database/settings.py

from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DATABASE_NAME


mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DATABASE_NAME]

settings_collection = db.settings


DEFAULT_SETTINGS = {
    "_id": "bot_settings",
    "maintenance_mode": False,
    "maintenance_message": "Bot is currently under maintenance. Please try again later.",
    "downloads_enabled": True,
    "uploads_enabled": True,
    "max_concurrent_downloads": 3,
    "max_downloads_per_user": 2,
    "max_queue_size": 100,
    "auto_retry": True,
    "max_retries": 3,
    "auto_cleanup": True,
    "cleanup_after_hours": 6,
    "force_subscribe": [],
    "allowed_websites": [],
    "blocked_websites": [],
    "log_channel": None,
    "auto_upload": False,
    "duplicate_check": True,
}


async def initialize_settings():
    await settings_collection.update_one(
        {"_id": "bot_settings"},
        {"$setOnInsert": DEFAULT_SETTINGS},
        upsert=True
    )


async def get_settings():
    settings = await settings_collection.find_one(
        {"_id": "bot_settings"}
    )

    if not settings:
        await initialize_settings()
        settings = await settings_collection.find_one(
            {"_id": "bot_settings"}
        )

    return settings


async def update_setting(key: str, value):
    if key == "_id":
        return False

    await settings_collection.update_one(
        {"_id": "bot_settings"},
        {"$set": {key: value}},
        upsert=True
    )
    return True


async def delete_setting(key: str):
    if key == "_id":
        return False

    await settings_collection.update_one(
        {"_id": "bot_settings"},
        {"$unset": {key: ""}}
    )
    return True


async def is_maintenance_enabled():
    settings = await get_settings()
    return settings.get("maintenance_mode", False)


async def set_maintenance(status: bool):
    return await update_setting("maintenance_mode", status)


async def is_downloads_enabled():
    settings = await get_settings()
    return settings.get("downloads_enabled", True)


async def is_uploads_enabled():
    settings = await get_settings()
    return settings.get("uploads_enabled", True)


async def get_allowed_websites():
    settings = await get_settings()
    return settings.get("allowed_websites", [])


async def get_blocked_websites():
    settings = await get_settings()
    return settings.get("blocked_websites", [])


async def get_log_channel():
    settings = await get_settings()
    return settings.get("log_channel")


async def reset_settings():
    await settings_collection.replace_one(
        {"_id": "bot_settings"},
        DEFAULT_SETTINGS,
        upsert=True
    )
    return True
