"""
Tests for the trade execution engine.
"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.models import User, Strategy, Alert, Trade, TradeStatus, AlertType, AlertSource
from app.services.trade_engine import TradeEngine, RiskManager
from app.tests.conftest import db_session, test_user_data, test_strategy_data, test_alert_data


@pytest.mark.asyncio
async def test_risk_manager_check_limits(db_session):
    """Test risk manager limit checks."""
    risk_manager = RiskManager()
    
    # Create test user
    user = User(
        email=test_user_data["email"],
        username=test_user_data["username"],
        hashed_password="hashed_password",
        created_at=datetime.utcnow()
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Test within limits
    is_ok, message = await risk_manager.check_risk_limits(
        db_session, user.id, "NSE:RELIANCE", "BUY", 10, 2500.0
    )
    assert is_ok
    assert "passed" in message
    
    # Test exceeding position size
    is_ok, message = await risk_manager.check_risk_limits(
        db_session, user.id, "NSE:RELIANCE", "BUY", 100, 2500.0
    )
    assert not is_ok
    assert "exceeds limit" in message


@pytest.mark.asyncio
async def test_trade_engine_process_alert(db_session, test_user_data, test_strategy_data, test_alert_data):
    """Test trade engine alert processing."""
    trade_engine = TradeEngine()
    
    # Create test user
    user = User(
        email=test_user_data["email"],
        username=test_user_data["username"],
        hashed_password="hashed_password",
        fyers_access_token="test_token",
        fyers_refresh_token="test_refresh",
        fyers_token_expires_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Create test strategy
    strategy = Strategy(
        user_id=user.id,
        name=test_strategy_data["name"],
        strategy_type=test_strategy_data["strategy_type"],
        parameters=test_strategy_data["parameters"],
        risk_parameters=test_strategy_data["risk_parameters"],
        entry_rules=test_strategy_data["entry_rules"],
        exit_rules=test_strategy_data["exit_rules"],
        position_sizing_rules=test_strategy_data["position_sizing_rules"],
        is_paper_trading=True,
        created_at=datetime.utcnow()
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    
    # Create test alert
    alert = Alert(
        user_id=user.id,
        symbol="RELIANCE",
        exchange="NSE",
        alert_type=AlertType.BUY,
        source=AlertSource.MANUAL,
        price=2500.0,
        quantity=10,
        message="Test signal",
        created_at=datetime.utcnow()
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    
    # Mock Fyers client
    with patch('app.services.trade_engine.FyersClient') as mock_fyers:
        mock_client = AsyncMock()
        mock_client.get_current_price.return_value = 2500.0
        mock_client.is_market_open.return_value = True
        mock_fyers.return_value = mock_client
        
        # Process alert
        success = await trade_engine.process_alert(alert.id, db_session)
        
        assert success
        assert alert.status.value == "processed"


@pytest.mark.asyncio
async def test_trade_engine_paper_trade_execution(db_session, test_user_data, test_strategy_data):
    """Test paper trade execution."""
    trade_engine = TradeEngine()
    
    # Create test user
    user = User(
        email=test_user_data["email"],
        username=test_user_data["username"],
        hashed_password="hashed_password",
        fyers_access_token="test_token",
        fyers_refresh_token="test_refresh",
        fyers_token_expires_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Create test strategy
    strategy = Strategy(
        user_id=user.id,
        name=test_strategy_data["name"],
        strategy_type=test_strategy_data["strategy_type"],
        parameters=test_strategy_data["parameters"],
        risk_parameters=test_strategy_data["risk_parameters"],
        entry_rules=test_strategy_data["entry_rules"],
        exit_rules=test_strategy_data["exit_rules"],
        position_sizing_rules=test_strategy_data["position_sizing_rules"],
        is_paper_trading=True,
        created_at=datetime.utcnow()
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    
    # Create test alert
    alert = Alert(
        user_id=user.id,
        symbol="RELIANCE",
        exchange="NSE",
        alert_type=AlertType.BUY,
        source=AlertSource.MANUAL,
        price=2500.0,
        quantity=10,
        message="Test signal",
        created_at=datetime.utcnow()
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    
    # Mock Fyers client
    with patch('app.services.trade_engine.FyersClient') as mock_fyers:
        mock_client = AsyncMock()
        mock_client.get_current_price.return_value = 2500.0
        mock_client.is_market_open.return_value = True
        mock_fyers.return_value = mock_client
        
        # Execute trade
        success = await trade_engine._execute_trade(alert, strategy, user, db_session)
        
        assert success
        
        # Check that trade was created
        trades_query = await db_session.execute(
            "SELECT * FROM trades WHERE user_id = :user_id",
            {"user_id": user.id}
        )
        trades = trades_query.fetchall()
        assert len(trades) == 1
        assert trades[0].symbol == "RELIANCE"
        assert trades[0].side.value == "buy"


@pytest.mark.asyncio
async def test_position_size_calculation(db_session, test_user_data, test_strategy_data):
    """Test position size calculation."""
    trade_engine = TradeEngine()
    
    # Create test user
    user = User(
        email=test_user_data["email"],
        username=test_user_data["username"],
        hashed_password="hashed_password",
        fyers_access_token="test_token",
        fyers_refresh_token="test_refresh",
        fyers_token_expires_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Create test strategy with fixed quantity
    strategy = Strategy(
        user_id=user.id,
        name=test_strategy_data["name"],
        strategy_type=test_strategy_data["strategy_type"],
        parameters=test_strategy_data["parameters"],
        risk_parameters=test_strategy_data["risk_parameters"],
        entry_rules=test_strategy_data["entry_rules"],
        exit_rules=test_strategy_data["exit_rules"],
        position_sizing_rules={"fixed_quantity": 5},
        is_paper_trading=True,
        created_at=datetime.utcnow()
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    
    # Create test alert
    alert = Alert(
        user_id=user.id,
        symbol="RELIANCE",
        exchange="NSE",
        alert_type=AlertType.BUY,
        source=AlertSource.MANUAL,
        price=2500.0,
        quantity=10,
        message="Test signal",
        created_at=datetime.utcnow()
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    
    # Mock Fyers client
    with patch('app.services.trade_engine.FyersClient') as mock_fyers:
        mock_client = AsyncMock()
        mock_client.get_current_price.return_value = 2500.0
        mock_client.get_funds.return_value = {"data": {"fund_limit": 100000}}
        mock_fyers.return_value = mock_client
        
        # Calculate position size
        quantity = await trade_engine._calculate_position_size(alert, strategy, user, db_session)
        
        assert quantity == 5  # Fixed quantity from strategy


@pytest.mark.asyncio
async def test_strategy_performance_update(db_session, test_user_data, test_strategy_data):
    """Test strategy performance metrics update."""
    trade_engine = TradeEngine()
    
    # Create test user
    user = User(
        email=test_user_data["email"],
        username=test_user_data["username"],
        hashed_password="hashed_password",
        created_at=datetime.utcnow()
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Create test strategy
    strategy = Strategy(
        user_id=user.id,
        name=test_strategy_data["name"],
        strategy_type=test_strategy_data["strategy_type"],
        parameters=test_strategy_data["parameters"],
        risk_parameters=test_strategy_data["risk_parameters"],
        entry_rules=test_strategy_data["entry_rules"],
        exit_rules=test_strategy_data["exit_rules"],
        position_sizing_rules=test_strategy_data["position_sizing_rules"],
        is_paper_trading=True,
        created_at=datetime.utcnow()
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    
    # Test performance update
    initial_trades = strategy.total_trades
    initial_pnl = strategy.total_pnl
    
    strategy.update_performance_metrics(100.0, True)  # Winning trade
    
    assert strategy.total_trades == initial_trades + 1
    assert strategy.total_pnl == initial_pnl + 100.0
    assert strategy.winning_trades == 1
    assert strategy.losing_trades == 0
    
    # Test losing trade
    strategy.update_performance_metrics(-50.0, False)  # Losing trade
    
    assert strategy.total_trades == initial_trades + 2
    assert strategy.total_pnl == initial_pnl + 50.0
    assert strategy.winning_trades == 1
    assert strategy.losing_trades == 1
