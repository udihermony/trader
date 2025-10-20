"""
Portfolio management routes.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from loguru import logger

from app.db import get_db
from app.models import User, Portfolio, Trade, TradeStatus
from app.routers.auth import get_current_active_user

router = APIRouter()


# Pydantic models
class PortfolioPosition(BaseModel):
    symbol: str
    exchange: str
    quantity: int
    average_price: Optional[float]
    current_price: Optional[float]
    market_value: Optional[float]
    invested_amount: Optional[float]
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    pnl_percentage: float
    first_trade_date: Optional[datetime]
    last_trade_date: Optional[datetime]
    trade_count: int


class PortfolioSummary(BaseModel):
    total_positions: int
    total_invested: float
    total_market_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    total_pnl: float
    total_pnl_percentage: float
    active_positions: int
    flat_positions: int


class TradeHistory(BaseModel):
    id: uuid.UUID
    symbol: str
    side: str
    quantity: int
    price: Optional[float]
    average_price: Optional[float]
    status: str
    realized_pnl: Optional[float]
    net_pnl: Optional[float]
    created_at: datetime
    filled_at: Optional[datetime]


class PortfolioResponse(BaseModel):
    positions: List[PortfolioPosition]
    summary: PortfolioSummary
    last_updated: datetime


@router.get("/", response_model=PortfolioResponse)
async def get_portfolio(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's portfolio."""
    try:
        # Get all positions
        positions_query = select(Portfolio).where(Portfolio.user_id == current_user.id)
        positions_result = await db.execute(positions_query)
        positions = positions_result.scalars().all()
        
        # Calculate summary
        total_invested = sum(p.invested_amount or 0 for p in positions)
        total_market_value = sum(p.market_value or 0 for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
        total_realized_pnl = sum(p.realized_pnl for p in positions)
        total_pnl = total_unrealized_pnl + total_realized_pnl
        
        total_pnl_percentage = (total_pnl / total_invested * 100) if total_invested > 0 else 0
        
        active_positions = sum(1 for p in positions if p.quantity != 0)
        flat_positions = len(positions) - active_positions
        
        summary = PortfolioSummary(
            total_positions=len(positions),
            total_invested=total_invested,
            total_market_value=total_market_value,
            total_unrealized_pnl=total_unrealized_pnl,
            total_realized_pnl=total_realized_pnl,
            total_pnl=total_pnl,
            total_pnl_percentage=total_pnl_percentage,
            active_positions=active_positions,
            flat_positions=flat_positions
        )
        
        position_responses = [
            PortfolioPosition(
                symbol=p.symbol,
                exchange=p.exchange,
                quantity=p.quantity,
                average_price=p.average_price,
                current_price=p.current_price,
                market_value=p.market_value,
                invested_amount=p.invested_amount,
                unrealized_pnl=p.unrealized_pnl,
                realized_pnl=p.realized_pnl,
                total_pnl=p.total_pnl,
                pnl_percentage=p.pnl_percentage,
                first_trade_date=p.first_trade_date,
                last_trade_date=p.last_trade_date,
                trade_count=p.trade_count
            )
            for p in positions
        ]
        
        return PortfolioResponse(
            positions=position_responses,
            summary=summary,
            last_updated=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get portfolio"
        )


@router.get("/positions/{symbol}")
async def get_position(
    symbol: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific position details."""
    try:
        position_query = select(Portfolio).where(
            Portfolio.user_id == current_user.id,
            Portfolio.symbol == symbol
        )
        position_result = await db.execute(position_query)
        position = position_result.scalar_one_or_none()
        
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position not found"
            )
        
        return PortfolioPosition(
            symbol=position.symbol,
            exchange=position.exchange,
            quantity=position.quantity,
            average_price=position.average_price,
            current_price=position.current_price,
            market_value=position.market_value,
            invested_amount=position.invested_amount,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            total_pnl=position.total_pnl,
            pnl_percentage=position.pnl_percentage,
            first_trade_date=position.first_trade_date,
            last_trade_date=position.last_trade_date,
            trade_count=position.trade_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get position"
        )


@router.get("/trades", response_model=List[TradeHistory])
async def get_trade_history(
    symbol: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    days: int = 30,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get trade history."""
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Build query
        trades_query = select(Trade).where(
            Trade.user_id == current_user.id,
            Trade.created_at >= start_date,
            Trade.created_at <= end_date
        )
        
        if symbol:
            trades_query = trades_query.where(Trade.symbol == symbol)
        
        trades_query = trades_query.order_by(Trade.created_at.desc()).offset(skip).limit(limit)
        
        trades_result = await db.execute(trades_query)
        trades = trades_result.scalars().all()
        
        return [
            TradeHistory(
                id=trade.id,
                symbol=trade.symbol,
                side=trade.side.value,
                quantity=trade.quantity,
                price=trade.price,
                average_price=trade.average_price,
                status=trade.status.value,
                realized_pnl=trade.realized_pnl,
                net_pnl=trade.net_pnl,
                created_at=trade.created_at,
                filled_at=trade.filled_at
            )
            for trade in trades
        ]
        
    except Exception as e:
        logger.error(f"Error getting trade history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get trade history"
        )


@router.get("/performance")
async def get_portfolio_performance(
    days: int = 30,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get portfolio performance metrics."""
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get trades in date range
        trades_query = select(Trade).where(
            Trade.user_id == current_user.id,
            Trade.created_at >= start_date,
            Trade.created_at <= end_date,
            Trade.status == TradeStatus.FILLED
        )
        trades_result = await db.execute(trades_query)
        trades = trades_result.scalars().all()
        
        # Calculate metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.net_pnl and t.net_pnl > 0)
        losing_trades = sum(1 for t in trades if t.net_pnl and t.net_pnl < 0)
        
        total_pnl = sum(t.net_pnl or 0 for t in trades)
        winning_pnl = sum(t.net_pnl or 0 for t in trades if t.net_pnl and t.net_pnl > 0)
        losing_pnl = sum(t.net_pnl or 0 for t in trades if t.net_pnl and t.net_pnl < 0)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        loss_rate = (losing_trades / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = (winning_pnl / winning_trades) if winning_trades > 0 else 0
        avg_loss = (losing_pnl / losing_trades) if losing_trades > 0 else 0
        
        profit_factor = abs(winning_pnl / losing_pnl) if losing_pnl != 0 else float('inf')
        
        # Calculate daily P&L
        daily_pnl = {}
        for trade in trades:
            if trade.filled_at:
                date_key = trade.filled_at.date()
                if date_key not in daily_pnl:
                    daily_pnl[date_key] = 0
                daily_pnl[date_key] += trade.net_pnl or 0
        
        # Calculate max drawdown
        running_pnl = 0
        max_pnl = 0
        max_drawdown = 0
        
        for date in sorted(daily_pnl.keys()):
            running_pnl += daily_pnl[date]
            max_pnl = max(max_pnl, running_pnl)
            drawdown = max_pnl - running_pnl
            max_drawdown = max(max_drawdown, drawdown)
        
        return {
            "period": f"{days} days",
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "total_pnl": total_pnl,
            "winning_pnl": winning_pnl,
            "losing_pnl": losing_pnl,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "daily_pnl": daily_pnl
        }
        
    except Exception as e:
        logger.error(f"Error getting portfolio performance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get portfolio performance"
        )


@router.post("/refresh")
async def refresh_portfolio(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Refresh portfolio with current market prices."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        from app.services.fyers_client import FyersClient
        
        fyers_client = FyersClient(current_user.fyers_access_token)
        
        # Get current positions from Fyers
        positions_data = await fyers_client.get_positions()
        
        if positions_data.get("data"):
            for position_data in positions_data["data"]:
                symbol = position_data.get("symbol", "")
                current_price = position_data.get("currentPrice", 0)
                
                # Update portfolio position
                portfolio_query = select(Portfolio).where(
                    Portfolio.user_id == current_user.id,
                    Portfolio.symbol == symbol
                )
                portfolio_result = await db.execute(portfolio_query)
                portfolio = portfolio_result.scalar_one_or_none()
                
                if portfolio:
                    portfolio.update_current_price(current_price)
        
        await db.commit()
        
        logger.info(f"Portfolio refreshed for user: {current_user.email}")
        
        return {"message": "Portfolio refreshed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing portfolio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh portfolio"
        )


@router.get("/summary")
async def get_portfolio_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get portfolio summary statistics."""
    try:
        # Get portfolio positions
        positions_query = select(Portfolio).where(Portfolio.user_id == current_user.id)
        positions_result = await db.execute(positions_query)
        positions = positions_result.scalars().all()
        
        # Get recent trades
        recent_trades_query = select(Trade).where(
            Trade.user_id == current_user.id,
            Trade.created_at >= datetime.utcnow() - timedelta(days=7)
        )
        recent_trades_result = await db.execute(recent_trades_query)
        recent_trades = recent_trades_result.scalars().all()
        
        # Calculate summary
        total_positions = len(positions)
        active_positions = sum(1 for p in positions if p.quantity != 0)
        total_invested = sum(p.invested_amount or 0 for p in positions)
        total_market_value = sum(p.market_value or 0 for p in positions)
        total_pnl = sum(p.total_pnl for p in positions)
        
        recent_trades_count = len(recent_trades)
        recent_pnl = sum(t.net_pnl or 0 for t in recent_trades)
        
        return {
            "total_positions": total_positions,
            "active_positions": active_positions,
            "total_invested": total_invested,
            "total_market_value": total_market_value,
            "total_pnl": total_pnl,
            "total_pnl_percentage": (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            "recent_trades_7d": recent_trades_count,
            "recent_pnl_7d": recent_pnl,
            "last_updated": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error getting portfolio summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get portfolio summary"
        )
