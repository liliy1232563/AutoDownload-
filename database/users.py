"""MongoDB user management for Anime Auto Downloader."""

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument


class UserDatabase:
    def __init__(self, database_url: str, database_name: str = "anime_downloader"):
        if not database_url:
            raise ValueError("DATABASE_URL is required")

        self.client = AsyncIOMotorClient(database_url)
        self.db = self.client[database_name]
        self.users = self.db["users"]

    async def setup(self):
        await self.users.create_index("user_id", unique=True)
        await self.users.create_index("is_admin")
        await self.users.create_index("is_premium")

    async def add_user(self, user_id: int, username: str = None):
        now = datetime.now(timezone.utc)

        return await self.users.find_one_and_update(
            {"user_id": int(user_id)},
            {
                "$set": {
                    "username": username,
                    "last_seen": now,
                },
                "$setOnInsert": {
                    "user_id": int(user_id),
                    "is_admin": False,
                    "is_premium": False,
                    "downloads": 0,
                    "joined_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    async def get_user(self, user_id: int):
        return await self.users.find_one({"user_id": int(user_id)})

    async def is_admin(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        return bool(user and user.get("is_admin", False))

    async def add_admin(self, user_id: int):
        return await self.users.update_one(
            {"user_id": int(user_id)},
            {"$set": {"is_admin": True}},
            upsert=True,
        )

    async def remove_admin(self, user_id: int):
        return await self.users.update_one(
            {"user_id": int(user_id)},
            {"$set": {"is_admin": False}},
        )

    async def get_admins(self) -> list[dict[str, Any]]:
        return await self.users.find(
            {"is_admin": True}
        ).to_list(length=500)

    async def set_premium(self, user_id: int, expires_at: datetime = None):
        return await self.users.update_one(
            {"user_id": int(user_id)},
            {
                "$set": {
                    "is_premium": True,
                    "premium_until": expires_at,
                }
            },
            upsert=True,
        )

    async def remove_premium(self, user_id: int):
        return await self.users.update_one(
            {"user_id": int(user_id)},
            {
                "$set": {
                    "is_premium": False,
                    "premium_until": None,
                }
            },
        )

    async def is_premium(self, user_id: int) -> bool:
        user = await self.get_user(user_id)

        if not user or not user.get("is_premium"):
            return False

        expires_at = user.get("premium_until")

        if expires_at is None:
            return True

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= datetime.now(timezone.utc):
            await self.remove_premium(user_id)
            return False

        return True

    async def increment_downloads(self, user_id: int):
        return await self.users.update_one(
            {"user_id": int(user_id)},
            {"$inc": {"downloads": 1}},
            upsert=True,
        )

    async def get_total_users(self) -> int:
        return await self.users.count_documents({})

    async def close(self):
        self.client.close()
