"""
Test configuration and utilities.
"""

import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.config import settings


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
    echo=False
)

# Create test session factory
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def setup_test_db():
    """Set up test database."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(setup_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def override_get_db(db_session: AsyncSession):
    """Override the get_db dependency."""
    async def _override_get_db():
        yield db_session
    return _override_get_db


@pytest.fixture
def test_user_data():
    """Test user data."""
    return {
        "email": "test@example.com",
        "username": "testuser",
        "full_name": "Test User",
        "password": "testpassword123"
    }


@pytest.fixture
def test_strategy_data():
    """Test strategy data."""
    return {
        "name": "Test Strategy",
        "description": "A test trading strategy",
        "strategy_type": "momentum",
        "parameters": {"lookback_period": 20},
        "risk_parameters": {"max_risk": 0.02},
        "entry_rules": {"condition": "price > sma"},
        "exit_rules": {"condition": "price < sma"},
        "position_sizing_rules": {"percentage_of_capital": 5},
        "max_position_size": 10000,
        "stop_loss_percentage": 2.0,
        "take_profit_percentage": 4.0,
        "max_daily_trades": 10,
        "is_paper_trading": True
    }


@pytest.fixture
def test_alert_data():
    """Test alert data."""
    return {
        "symbol": "NSE:RELIANCE",
        "exchange": "NSE",
        "alert_type": "buy",
        "source": "chartlink",
        "price": 2500.50,
        "quantity": 10,
        "message": "Test buy signal",
        "metadata": {"test": True}
    }
