
# tests/test_jobs.py

import pytest
from unittest.mock import AsyncMock, patch

from database import jobs


@pytest.fixture
def mock_collection():
    return AsyncMock()


@pytest.mark.asyncio
async def test_create_job(mock_collection):
    mock_collection.insert_one = AsyncMock()

    with patch.object(jobs, "jobs_collection", mock_collection):
        result = await jobs.create_job(
            user_id=12345,
            url="https://example.com/anime/episode-1"
        )

    assert result is not None
    mock_collection.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_get_job(mock_collection):
    expected_job = {
        "_id": "job123",
        "user_id": 12345,
        "status": "queued"
    }

    mock_collection.find_one = AsyncMock(
        return_value=expected_job
    )

    with patch.object(jobs, "jobs_collection", mock_collection):
        result = await jobs.get_job("job123")

    assert result == expected_job


@pytest.mark.asyncio
async def test_update_job_status(mock_collection):
    mock_collection.update_one = AsyncMock()

    with patch.object(jobs, "jobs_collection", mock_collection):
        result = await jobs.update_job_status(
            "job123",
            "downloading"
        )

    assert result is not None
    mock_collection.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_job(mock_collection):
    mock_collection.update_one = AsyncMock()

    with patch.object(jobs, "jobs_collection", mock_collection):
        result = await jobs.cancel_job("job123")

    assert result is not None
    mock_collection.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_get_user_jobs(mock_collection):
    expected_jobs = [
        {"_id": "job1", "user_id": 12345},
        {"_id": "job2", "user_id": 12345}
    ]

    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=expected_jobs)
    mock_collection.find = AsyncMock(return_value=cursor)

    with patch.object(jobs, "jobs_collection", mock_collection):
        result = await jobs.get_user_jobs(12345)

    assert result == expected_jobs


@pytest.mark.asyncio
async def test_delete_job(mock_collection):
    mock_collection.delete_one = AsyncMock()

    with patch.object(jobs, "jobs_collection", mock_collection):
        result = await jobs.delete_job("job123")

    assert result is not None
    mock_collection.delete_one.assert_called_once()
      
