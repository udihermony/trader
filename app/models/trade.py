"""
Trade model for order execution and trade tracking.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Float, Integer, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from app.db import Base


class TradeStatus(str, enum.Enum):
    """Trade status enumeration."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class OrderType(str, enum.Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, enum.Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class Trade(Base):
    """Trade model for order execution and trade tracking."""
    
    __tablename__ = "trades"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)
    alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("alerts.id"), nullable=True)
    
    # Trade information
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), nullable=False)
    
    # Order details
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # For limit orders
    stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # For stop orders
    
    # Execution details
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Fyers API details
    fyers_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    fyers_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    fyers_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Trade status and timing
    status: Mapped[TradeStatus] = mapped_column(Enum(TradeStatus), default=TradeStatus.PENDING, nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # P&L and fees
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    brokerage_fee: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    taxes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Risk management
    stop_loss_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Comma-separated tags
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="trades")
    strategy = relationship("Strategy", back_populates="trades")
    alert = relationship("Alert", back_populates="trades")
    
    def __repr__(self) -> str:
        return f"<Trade(id={self.id}, symbol={self.symbol}, side={self.side}, status={self.status})>"
    
    @property
    def is_filled(self) -> bool:
        """Check if trade is completely filled."""
        return self.status == TradeStatus.FILLED and self.filled_quantity == self.quantity
    
    @property
    def is_partially_filled(self) -> bool:
        """Check if trade is partially filled."""
        return self.status == TradeStatus.PARTIALLY_FILLED or (
            self.status == TradeStatus.FILLED and self.filled_quantity < self.quantity
        )
    
    @property
    def is_pending(self) -> bool:
        """Check if trade is still pending."""
        return self.status in [TradeStatus.PENDING, TradeStatus.SUBMITTED]
    
    @property
    def is_cancelled(self) -> bool:
        """Check if trade is cancelled."""
        return self.status in [TradeStatus.CANCELLED, TradeStatus.REJECTED, TradeStatus.FAILED]
    
    def calculate_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L based on current price."""
        if not self.is_filled or not self.average_price:
            return 0.0
        
        if self.side == OrderSide.BUY:
            return (current_price - self.average_price) * self.filled_quantity
        else:  # SELL
            return (self.average_price - current_price) * self.filled_quantity
    
    def update_execution(self, filled_qty: int, avg_price: float, fyers_status: str):
        """Update trade execution details."""
        self.filled_quantity = filled_qty
        self.average_price = avg_price
        self.fyers_status = fyers_status
        self.total_amount = filled_qty * avg_price
        
        if filled_qty == self.quantity:
            self.status = TradeStatus.FILLED
            self.filled_at = datetime.utcnow()
        elif filled_qty > 0:
            self.status = TradeStatus.PARTIALLY_FILLED
        
        self.updated_at = datetime.utcnow()
