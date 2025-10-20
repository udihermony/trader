"""
Strategy management routes.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from pydantic import BaseModel, Field
from loguru import logger

from app.db import get_db
from app.models import User, Strategy, Trade
from app.routers.auth import get_current_active_user

router = APIRouter()


# Pydantic models
class StrategyCreate(BaseModel):
    name: str = Field(..., description="Strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    strategy_type: str = Field(..., description="Strategy type")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    risk_parameters: Dict[str, Any] = Field(default_factory=dict, description="Risk parameters")
    entry_rules: Dict[str, Any] = Field(default_factory=dict, description="Entry rules")
    exit_rules: Dict[str, Any] = Field(default_factory=dict, description="Exit rules")
    position_sizing_rules: Dict[str, Any] = Field(default_factory=dict, description="Position sizing rules")
    max_position_size: Optional[float] = Field(None, description="Maximum position size")
    stop_loss_percentage: Optional[float] = Field(None, description="Stop loss percentage")
    take_profit_percentage: Optional[float] = Field(None, description="Take profit percentage")
    max_daily_trades: Optional[int] = Field(None, description="Maximum daily trades")
    is_paper_trading: bool = Field(True, description="Paper trading mode")


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    strategy_type: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    risk_parameters: Optional[Dict[str, Any]] = None
    entry_rules: Optional[Dict[str, Any]] = None
    exit_rules: Optional[Dict[str, Any]] = None
    position_sizing_rules: Optional[Dict[str, Any]] = None
    max_position_size: Optional[float] = None
    stop_loss_percentage: Optional[float] = None
    take_profit_percentage: Optional[float] = None
    max_daily_trades: Optional[int] = None
    is_active: Optional[bool] = None
    is_paper_trading: Optional[bool] = None


class StrategyResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    strategy_type: str
    parameters: Dict[str, Any]
    risk_parameters: Dict[str, Any]
    entry_rules: Dict[str, Any]
    exit_rules: Dict[str, Any]
    position_sizing_rules: Dict[str, Any]
    max_position_size: Optional[float]
    stop_loss_percentage: Optional[float]
    take_profit_percentage: Optional[float]
    max_daily_trades: Optional[int]
    is_active: bool
    is_paper_trading: bool
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    win_rate: float
    loss_rate: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    created_at: datetime
    updated_at: datetime
    last_executed_at: Optional[datetime]


class StrategyListResponse(BaseModel):
    strategies: List[StrategyResponse]
    total: int


@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    strategy_data: StrategyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new trading strategy."""
    try:
        # Check if strategy name already exists for user
        existing_strategy_query = select(Strategy).where(
            Strategy.user_id == current_user.id,
            Strategy.name == strategy_data.name
        )
        existing_strategy_result = await db.execute(existing_strategy_query)
        existing_strategy = existing_strategy_result.scalar_one_or_none()
        
        if existing_strategy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Strategy with this name already exists"
            )
        
        # Create new strategy
        strategy = Strategy(
            user_id=current_user.id,
            name=strategy_data.name,
            description=strategy_data.description,
            strategy_type=strategy_data.strategy_type,
            parameters=strategy_data.parameters,
            risk_parameters=strategy_data.risk_parameters,
            entry_rules=strategy_data.entry_rules,
            exit_rules=strategy_data.exit_rules,
            position_sizing_rules=strategy_data.position_sizing_rules,
            max_position_size=strategy_data.max_position_size,
            stop_loss_percentage=strategy_data.stop_loss_percentage,
            take_profit_percentage=strategy_data.take_profit_percentage,
            max_daily_trades=strategy_data.max_daily_trades,
            is_active=True,
            is_paper_trading=strategy_data.is_paper_trading,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        
        logger.info(f"Strategy created: {strategy.name} for user {current_user.email}")
        
        return StrategyResponse(
            id=strategy.id,
            name=strategy.name,
            description=strategy.description,
            strategy_type=strategy.strategy_type,
            parameters=strategy.parameters,
            risk_parameters=strategy.risk_parameters,
            entry_rules=strategy.entry_rules,
            exit_rules=strategy.exit_rules,
            position_sizing_rules=strategy.position_sizing_rules,
            max_position_size=strategy.max_position_size,
            stop_loss_percentage=strategy.stop_loss_percentage,
            take_profit_percentage=strategy.take_profit_percentage,
            max_daily_trades=strategy.max_daily_trades,
            is_active=strategy.is_active,
            is_paper_trading=strategy.is_paper_trading,
            total_trades=strategy.total_trades,
            winning_trades=strategy.winning_trades,
            losing_trades=strategy.losing_trades,
            total_pnl=strategy.total_pnl,
            win_rate=strategy.win_rate,
            loss_rate=strategy.loss_rate,
            max_drawdown=strategy.max_drawdown,
            sharpe_ratio=strategy.sharpe_ratio,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            last_executed_at=strategy.last_executed_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create strategy"
        )


@router.get("/", response_model=StrategyListResponse)
async def get_strategies(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's trading strategies."""
    try:
        query = select(Strategy).where(Strategy.user_id == current_user.id)
        
        if active_only:
            query = query.where(Strategy.is_active == True)
        
        query = query.order_by(Strategy.created_at.desc()).offset(skip).limit(limit)
        
        strategies_result = await db.execute(query)
        strategies = strategies_result.scalars().all()
        
        strategy_responses = [
            StrategyResponse(
                id=strategy.id,
                name=strategy.name,
                description=strategy.description,
                strategy_type=strategy.strategy_type,
                parameters=strategy.parameters,
                risk_parameters=strategy.risk_parameters,
                entry_rules=strategy.entry_rules,
                exit_rules=strategy.exit_rules,
                position_sizing_rules=strategy.position_sizing_rules,
                max_position_size=strategy.max_position_size,
                stop_loss_percentage=strategy.stop_loss_percentage,
                take_profit_percentage=strategy.take_profit_percentage,
                max_daily_trades=strategy.max_daily_trades,
                is_active=strategy.is_active,
                is_paper_trading=strategy.is_paper_trading,
                total_trades=strategy.total_trades,
                winning_trades=strategy.winning_trades,
                losing_trades=strategy.losing_trades,
                total_pnl=strategy.total_pnl,
                win_rate=strategy.win_rate,
                loss_rate=strategy.loss_rate,
                max_drawdown=strategy.max_drawdown,
                sharpe_ratio=strategy.sharpe_ratio,
                created_at=strategy.created_at,
                updated_at=strategy.updated_at,
                last_executed_at=strategy.last_executed_at
            )
            for strategy in strategies
        ]
        
        return StrategyListResponse(
            strategies=strategy_responses,
            total=len(strategy_responses)
        )
        
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get strategies"
        )


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific strategy."""
    try:
        strategy_query = select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id
        )
        strategy_result = await db.execute(strategy_query)
        strategy = strategy_result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        return StrategyResponse(
            id=strategy.id,
            name=strategy.name,
            description=strategy.description,
            strategy_type=strategy.strategy_type,
            parameters=strategy.parameters,
            risk_parameters=strategy.risk_parameters,
            entry_rules=strategy.entry_rules,
            exit_rules=strategy.exit_rules,
            position_sizing_rules=strategy.position_sizing_rules,
            max_position_size=strategy.max_position_size,
            stop_loss_percentage=strategy.stop_loss_percentage,
            take_profit_percentage=strategy.take_profit_percentage,
            max_daily_trades=strategy.max_daily_trades,
            is_active=strategy.is_active,
            is_paper_trading=strategy.is_paper_trading,
            total_trades=strategy.total_trades,
            winning_trades=strategy.winning_trades,
            losing_trades=strategy.losing_trades,
            total_pnl=strategy.total_pnl,
            win_rate=strategy.win_rate,
            loss_rate=strategy.loss_rate,
            max_drawdown=strategy.max_drawdown,
            sharpe_ratio=strategy.sharpe_ratio,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            last_executed_at=strategy.last_executed_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get strategy"
        )


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: uuid.UUID,
    strategy_data: StrategyUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a strategy."""
    try:
        strategy_query = select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id
        )
        strategy_result = await db.execute(strategy_query)
        strategy = strategy_result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        # Update fields
        update_data = strategy_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(strategy, field, value)
        
        strategy.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(strategy)
        
        logger.info(f"Strategy updated: {strategy.name}")
        
        return StrategyResponse(
            id=strategy.id,
            name=strategy.name,
            description=strategy.description,
            strategy_type=strategy.strategy_type,
            parameters=strategy.parameters,
            risk_parameters=strategy.risk_parameters,
            entry_rules=strategy.entry_rules,
            exit_rules=strategy.exit_rules,
            position_sizing_rules=strategy.position_sizing_rules,
            max_position_size=strategy.max_position_size,
            stop_loss_percentage=strategy.stop_loss_percentage,
            take_profit_percentage=strategy.take_profit_percentage,
            max_daily_trades=strategy.max_daily_trades,
            is_active=strategy.is_active,
            is_paper_trading=strategy.is_paper_trading,
            total_trades=strategy.total_trades,
            winning_trades=strategy.winning_trades,
            losing_trades=strategy.losing_trades,
            total_pnl=strategy.total_pnl,
            win_rate=strategy.win_rate,
            loss_rate=strategy.loss_rate,
            max_drawdown=strategy.max_drawdown,
            sharpe_ratio=strategy.sharpe_ratio,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            last_executed_at=strategy.last_executed_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update strategy"
        )


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a strategy."""
    try:
        strategy_query = select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id
        )
        strategy_result = await db.execute(strategy_query)
        strategy = strategy_result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        await db.delete(strategy)
        await db.commit()
        
        logger.info(f"Strategy deleted: {strategy.name}")
        
        return {"message": "Strategy deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete strategy"
        )


@router.get("/{strategy_id}/trades")
async def get_strategy_trades(
    strategy_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get trades for a specific strategy."""
    try:
        # Verify strategy belongs to user
        strategy_query = select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id
        )
        strategy_result = await db.execute(strategy_query)
        strategy = strategy_result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        # Get trades
        trades_query = select(Trade).where(
            Trade.strategy_id == strategy_id
        ).order_by(Trade.created_at.desc()).offset(skip).limit(limit)
        
        trades_result = await db.execute(trades_query)
        trades = trades_result.scalars().all()
        
        return {
            "trades": [
                {
                    "id": trade.id,
                    "symbol": trade.symbol,
                    "side": trade.side.value,
                    "quantity": trade.quantity,
                    "price": trade.price,
                    "status": trade.status.value,
                    "created_at": trade.created_at,
                    "filled_at": trade.filled_at,
                    "realized_pnl": trade.realized_pnl
                }
                for trade in trades
            ],
            "total": len(trades)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy trades: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get strategy trades"
        )


@router.post("/{strategy_id}/activate")
async def activate_strategy(
    strategy_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Activate a strategy."""
    try:
        strategy_query = select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id
        )
        strategy_result = await db.execute(strategy_query)
        strategy = strategy_result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        strategy.is_active = True
        strategy.updated_at = datetime.utcnow()
        
        await db.commit()
        
        logger.info(f"Strategy activated: {strategy.name}")
        
        return {"message": "Strategy activated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate strategy"
        )


@router.post("/{strategy_id}/deactivate")
async def deactivate_strategy(
    strategy_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a strategy."""
    try:
        strategy_query = select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id
        )
        strategy_result = await db.execute(strategy_query)
        strategy = strategy_result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found"
            )
        
        strategy.is_active = False
        strategy.updated_at = datetime.utcnow()
        
        await db.commit()
        
        logger.info(f"Strategy deactivated: {strategy.name}")
        
        return {"message": "Strategy deactivated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate strategy"
        )
