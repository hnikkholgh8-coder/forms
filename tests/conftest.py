#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pytest Configuration & Shared Fixtures for Exir Pooyan Tests.
"""

import pytest
import asyncio
import logging
from uuid import uuid4

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def sample_user_id():
    """Generate sample user UUID."""
    return uuid4()

@pytest.fixture
def sample_work_order_id():
    """Generate sample work order UUID."""
    return uuid4()

@pytest.fixture
def sample_task_order_id():
    """Generate sample task order UUID."""
    return uuid4()

@pytest.fixture
async def mock_postgres_pool():
    """Mock PostgreSQL connection pool for testing."""
    from unittest.mock import AsyncMock, MagicMock
    
    mock_pool = MagicMock()
    mock_pool.acquire = AsyncMock()
    mock_pool.close = AsyncMock()
    
    yield mock_pool

@pytest.fixture
async def mock_directus_client():
    """Mock Directus HTTP client for testing."""
    from unittest.mock import AsyncMock
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=200, json=lambda: {"data": []}))
    mock_client.post = AsyncMock(return_value=MagicMock(status_code=201, json=lambda: {"data": {"id": uuid4()}}))
    mock_client.patch = AsyncMock(return_value=MagicMock(status_code=200))
    mock_client.delete = AsyncMock(return_value=MagicMock(status_code=204))
    
    yield mock_client
