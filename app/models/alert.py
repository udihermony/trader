"""
Alert model for external trading signals and notifications.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Float, Integer, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from app.db import Base


class AlertStatus(str, enum.Enum):
    """Alert status enumeration."""
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED = "ignored"


class AlertType(str, enum.Enum):
    """Alert type enumeration."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class AlertSource(str, enum.Enum):
    """Alert source enumeration."""
    CHARTLINK = "chartlink"
    MANUAL = "manual"
    SYSTEM = "system"
    WEBHOOK = "webhook"


class Alert(Base):
    """Alert model for external trading signals and notifications."""
    
    __tablename__ = "alerts"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Alert information
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType), nullable=False)
    source: Mapped[AlertSource] = mapped_column(Enum(AlertSource), nullable=False)
    
    # Alert data
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    
    # Processing information
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.RECEIVED, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Strategy matching
    matched_strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 to 1.0
    
    # External reference
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    external_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="alerts")
    matched_strategy = relationship("Strategy", foreign_keys=[matched_strategy_id])
    trades = relationship("Trade", back_populates="alert", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, symbol={self.symbol}, type={self.alert_type}, status={self.status})>"
    
    @property
    def is_processed(self) -> bool:
        """Check if alert has been processed."""
        return self.status in [AlertStatus.PROCESSED, AlertStatus.FAILED, AlertStatus.IGNORED]
    
    @property
    def is_actionable(self) -> bool:
        """Check if alert is actionable (BUY or SELL)."""
        return self.alert_type in [AlertType.BUY, AlertType.SELL]
    
    def mark_as_processing(self):
        """Mark alert as being processed."""
        self.status = AlertStatus.PROCESSING
        self.updated_at = datetime.utcnow()
    
    def mark_as_processed(self, strategy_id: Optional[uuid.UUID] = None, confidence: Optional[float] = None):
        """Mark alert as successfully processed."""
        self.status = AlertStatus.PROCESSED
        self.processed_at = datetime.utcnow()
        if strategy_id:
            self.matched_strategy_id = strategy_id
        if confidence is not None:
            self.confidence_score = confidence
        self.updated_at = datetime.utcnow()
    
    def mark_as_failed(self, error_message: str):
        """Mark alert as failed processing."""
        self.status = AlertStatus.FAILED
        self.error_message = error_message
        self.processed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def mark_as_ignored(self, reason: str = "No matching strategy found"):
        """Mark alert as ignored."""
        self.status = AlertStatus.IGNORED
        self.error_message = reason
        self.processed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def to_trade_signal(self) -> Dict[str, Any]:
        """Convert alert to trade signal format."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.alert_type.value,
            "price": self.price,
            "quantity": self.quantity,
            "message": self.message,
            "metadata": self.metadata,
            "confidence": self.confidence_score,
            "source": self.source.value
        }
