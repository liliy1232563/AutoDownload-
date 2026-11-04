"""Anime search index database."""

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, ReturnDocument


class AnimeIndexDatabase:
    def __init__(
        self,
        database_url: str,
        database_name: str = "anime_downloader",
    ):
        if not database_url:
            raise ValueError("DATABASE_URL is required")

        self.client = AsyncIOMotorClient(database_url)
        self.db = self.client[database_name]
        self.anime = self.db["anime_index"]

    async def setup(self):
        await self.anime.create_index(
            [("anime_id", ASCENDING)],
            unique=True,
        )
        await self.anime.create_index(
            [("title", ASCENDING)]
        )
        await self.anime.create_index(
            [("normalized_title", ASCENDING)]
        )
        await self.anime.create_index(
            [("updated_at", DESCENDING)]
        )

    async def add_anime(
        self,
        anime_id: str,
        title: str,
        url: str | None = None,
        image: str | None = None,
        description: str | None = None,
        episodes: list[dict[str, Any]] | None = None,
        source: str | None = None,
    ):
        now = datetime.now(timezone.utc)
        normalized = " ".join(title.casefold().split())

        document = {
            "anime_id": str(anime_id),
            "title": title.strip(),
            "normalized_title": normalized,
            "url": url,
            "image": image,
            "description": description,
            "episodes": episodes or [],
            "source": source,
            "updated_at": now,
        }

        return await self.anime.find_one_and_update(
            {"anime_id": str(anime_id)},
            {
                "$set": document,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    async def get_anime(self, anime_id: str):
        return await self.anime.find_one(
            {"anime_id": str(anime_id)}
        )

    async def search_anime(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = " ".join(query.casefold().split())

        if not query:
            return []

        limit = max(1, min(int(limit), 50))

        # Prefer exact and prefix matches before broader substring matches.
        cursor = self.anime.find(
            {"normalized_title": {"$regex": f"^{self._escape(query)}"}}
        ).limit(limit)

        results = await cursor.to_list(length=limit)

        if len(results) < limit:
            existing_ids = [
                item["anime_id"] for item in results
            ]

            remaining = limit - len(results)

            cursor = self.anime.find({
                "normalized_title": {
                    "$regex": self._escape(query)
                },
                "anime_id": {"$nin": existing_ids},
            }).limit(remaining)

            results.extend(
                await cursor.to_list(length=remaining)
            )

        return results

    @staticmethod
    def _escape(value: str) -> str:
        import re
        return re.escape(value)

    async def add_episode(
        self,
        anime_id: str,
        episode: dict[str, Any],
    ):
        return await self.anime.update_one(
            {"anime_id": str(anime_id)},
            {
                "$addToSet": {"episodes": episode},
                "$set": {
                    "updated_at": datetime.now(timezone.utc)
                },
            },
        )

    async def delete_anime(self, anime_id: str):
        return await self.anime.delete_one(
            {"anime_id": str(anime_id)}
        )

    async def get_total_anime(self) -> int:
        return await self.anime.count_documents({})

    async def close(self):
        self.client.close()
