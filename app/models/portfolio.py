"""
Portfolio model for position tracking and portfolio management.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Float, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db import Base


class Portfolio(Base):
    """Portfolio model for position tracking and portfolio management."""
    
    __tablename__ = "portfolios"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Position information
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Position details
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # P&L calculations
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Position value
    market_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invested_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Risk metrics
    stop_loss_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Position metadata
    first_trade_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_trade_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    trade_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Additional data
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User")
    
    def __repr__(self) -> str:
        return f"<Portfolio(id={self.id}, symbol={self.symbol}, quantity={self.quantity})>"
    
    @property
    def is_long_position(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0
    
    @property
    def is_short_position(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0
    
    @property
    def is_flat(self) -> bool:
        """Check if position is flat."""
        return self.quantity == 0
    
    @property
    def position_value(self) -> float:
        """Calculate current position value."""
        if self.current_price is None or self.quantity == 0:
            return 0.0
        return abs(self.quantity) * self.current_price
    
    @property
    def pnl_percentage(self) -> float:
        """Calculate P&L percentage."""
        if self.invested_amount is None or self.invested_amount == 0:
            return 0.0
        return (self.total_pnl / self.invested_amount) * 100
    
    def update_position(self, trade_quantity: int, trade_price: float, trade_date: datetime):
        """Update position based on a new trade."""
        old_quantity = self.quantity
        old_average_price = self.average_price
        
        # Update quantity
        self.quantity += trade_quantity
        
        # Update average price
        if self.quantity == 0:
            self.average_price = None
            self.invested_amount = 0.0
        elif old_quantity == 0:
            self.average_price = trade_price
            self.invested_amount = abs(self.quantity) * trade_price
        else:
            # Calculate new average price
            old_value = old_quantity * (old_average_price or 0)
            new_value = trade_quantity * trade_price
            total_value = old_value + new_value
            self.average_price = total_value / self.quantity
            self.invested_amount = abs(self.quantity) * self.average_price
        
        # Update trade count and dates
        self.trade_count += 1
        if self.first_trade_date is None:
            self.first_trade_date = trade_date
        self.last_trade_date = trade_date
        
        # Calculate realized P&L if position is reduced or closed
        if abs(self.quantity) < abs(old_quantity):
            if old_quantity > 0 and trade_quantity < 0:  # Reducing long position
                realized_pnl = (trade_price - (old_average_price or 0)) * abs(trade_quantity)
            elif old_quantity < 0 and trade_quantity > 0:  # Reducing short position
                realized_pnl = ((old_average_price or 0) - trade_price) * abs(trade_quantity)
            else:
                realized_pnl = 0.0
            
            self.realized_pnl += realized_pnl
        
        self.updated_at = datetime.utcnow()
    
    def update_current_price(self, current_price: float):
        """Update current price and recalculate unrealized P&L."""
        self.current_price = current_price
        
        if self.quantity != 0 and self.average_price is not None:
            if self.quantity > 0:  # Long position
                self.unrealized_pnl = (current_price - self.average_price) * self.quantity
            else:  # Short position
                self.unrealized_pnl = (self.average_price - current_price) * abs(self.quantity)
            
            self.market_value = abs(self.quantity) * current_price
            self.total_pnl = self.realized_pnl + self.unrealized_pnl
        
        self.updated_at = datetime.utcnow()
    
    def set_stop_loss(self, stop_loss_price: float):
        """Set stop loss price for the position."""
        self.stop_loss_price = stop_loss_price
        self.updated_at = datetime.utcnow()
    
    def set_take_profit(self, take_profit_price: float):
        """Set take profit price for the position."""
        self.take_profit_price = take_profit_price
        self.updated_at = datetime.utcnow()
    
    def is_stop_loss_triggered(self) -> bool:
        """Check if stop loss is triggered."""
        if self.stop_loss_price is None or self.current_price is None:
            return False
        
        if self.quantity > 0:  # Long position
            return self.current_price <= self.stop_loss_price
        else:  # Short position
            return self.current_price >= self.stop_loss_price
    
    def is_take_profit_triggered(self) -> bool:
        """Check if take profit is triggered."""
        if self.take_profit_price is None or self.current_price is None:
            return False
        
        if self.quantity > 0:  # Long position
            return self.current_price >= self.take_profit_price
        else:  # Short position
            return self.current_price <= self.take_profit_price
