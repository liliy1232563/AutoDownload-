
# tests/test_permissions.py

import pytest
from unittest.mock import AsyncMock, patch

from database import users


@pytest.mark.asyncio
async def test_admin_permission():
    with patch.object(users, "ADMINS", [12345]):
        assert await users.is_admin(12345) is True


@pytest.mark.asyncio
async def test_normal_user_not_admin():
    with patch.object(users, "ADMINS", [12345]):
        assert await users.is_admin(67890) is False


@pytest.mark.asyncio
async def test_banned_user():
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(
        return_value={"user_id": 12345, "is_banned": True}
    )

    with patch.object(users, "users_collection", mock_collection):
        result = await users.is_banned(12345)

    assert result is True


@pytest.mark.asyncio
async def test_not_banned_user():
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value=None)

    with patch.object(users, "users_collection", mock_collection):
        result = await users.is_banned(12345)

    assert result is False


@pytest.mark.asyncio
async def test_premium_user():
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(
        return_value={"user_id": 12345, "is_premium": True}
    )

    with patch.object(users, "users_collection", mock_collection):
        result = await users.is_premium(12345)

    assert result is True


@pytest.mark.asyncio
async def test_normal_user_not_premium():
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(
        return_value={"user_id": 12345, "is_premium": False}
    )

    with patch.object(users, "users_collection", mock_collection):
        result = await users.is_premium(12345)

    assert result is False


@pytest.mark.asyncio
async def test_missing_user_not_premium():
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value=None)

    with patch.object(users, "users_collection", mock_collection):
        result = await users.is_premium(12345)

    assert result is False
      
