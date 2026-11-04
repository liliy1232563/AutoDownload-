"""MongoDB job storage for Anime Auto Downloader."""

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, ReturnDocument


class JobDatabase:
    def __init__(
        self,
        database_url: str,
        database_name: str = "anime_downloader",
    ):
        if not database_url:
            raise ValueError("DATABASE_URL is required")

        self.client = AsyncIOMotorClient(database_url)
        self.db = self.client[database_name]
        self.jobs = self.db["jobs"]

    async def setup(self):
        await self.jobs.create_index(
            [("job_id", ASCENDING)],
            unique=True,
        )
        await self.jobs.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        await self.jobs.create_index(
            [("status", ASCENDING)]
        )

    async def create_job(
        self,
        job_id: str,
        user_id: int,
        url: str,
        status: str = "queued",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)

        job = {
            "job_id": str(job_id),
            "user_id": int(user_id),
            "url": url,
            "status": status,
            "progress": 0,
            "file_path": None,
            "file_name": None,
            "file_size": 0,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }

        await self.jobs.insert_one(job)
        return job

    async def get_job(self, job_id: str):
        return await self.jobs.find_one(
            {"job_id": str(job_id)}
        )

    async def update_status(
        self,
        job_id: str,
        status: str,
        error: str | None = None,
    ):
        now = datetime.now(timezone.utc)

        update = {
            "status": status,
            "updated_at": now,
            "error": error,
        }

        if status in {"completed", "failed", "cancelled"}:
            update["completed_at"] = now

        return await self.jobs.find_one_and_update(
            {"job_id": str(job_id)},
            {"$set": update},
            return_document=ReturnDocument.AFTER,
        )

    async def update_progress(
        self,
        job_id: str,
        progress: float,
    ):
        progress = max(0, min(100, float(progress)))

        return await self.jobs.update_one(
            {"job_id": str(job_id)},
            {
                "$set": {
                    "progress": progress,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def update_file(
        self,
        job_id: str,
        file_path: str,
        file_name: str,
        file_size: int,
    ):
        return await self.jobs.update_one(
            {"job_id": str(job_id)},
            {
                "$set": {
                    "file_path": file_path,
                    "file_name": file_name,
                    "file_size": int(file_size),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def get_user_jobs(
        self,
        user_id: int,
        limit: int = 10,
    ):
        cursor = (
            self.jobs.find({"user_id": int(user_id)})
            .sort("created_at", DESCENDING)
            .limit(max(1, min(int(limit), 100)))
        )

        return await cursor.to_list(length=None)

    async def get_active_jobs(self):
        cursor = self.jobs.find(
            {"status": {"$in": ["queued", "downloading", "uploading"]}}
        ).sort("created_at", ASCENDING)

        return await cursor.to_list(length=500)

    async def delete_job(self, job_id: str):
        return await self.jobs.delete_one(
            {"job_id": str(job_id)}
        )

    async def get_total_jobs(self) -> int:
        return await self.jobs.count_documents({})

    async def close(self):
        self.client.close()
