"""
Strategy model for trading strategy management.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Float, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db import Base


class Strategy(Base):
    """Trading strategy model for strategy management and execution."""
    
    __tablename__ = "strategies"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Strategy information
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strategy_type: Mapped[str] = mapped_column(String(100), nullable=False)  # momentum, mean_reversion, breakout, etc.
    
    # Strategy configuration
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    risk_parameters: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    
    # Trading rules
    entry_rules: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    exit_rules: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    position_sizing_rules: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    
    # Risk management
    max_position_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_daily_trades: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Strategy status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_paper_trading: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Performance metrics
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="strategies")
    trades = relationship("Trade", back_populates="strategy", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Strategy(id={self.id}, name={self.name}, type={self.strategy_type})>"
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    @property
    def loss_rate(self) -> float:
        """Calculate loss rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.losing_trades / self.total_trades) * 100
    
    def update_performance_metrics(self, trade_pnl: float, is_winning: bool):
        """Update strategy performance metrics after a trade."""
        self.total_trades += 1
        self.total_pnl += trade_pnl
        
        if is_winning:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        # Update max drawdown if current PnL is negative
        if self.total_pnl < 0 and abs(self.total_pnl) > self.max_drawdown:
            self.max_drawdown = abs(self.total_pnl)
        
        self.last_executed_at = datetime.utcnow()
    
    def is_risk_limits_exceeded(self, current_position_size: float, daily_trades: int) -> bool:
        """Check if strategy risk limits are exceeded."""
        if self.max_position_size and current_position_size > self.max_position_size:
            return True
        if self.max_daily_trades and daily_trades >= self.max_daily_trades:
            return True
        return False
