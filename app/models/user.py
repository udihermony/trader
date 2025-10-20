"""
User model for authentication and user management.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db import Base


class User(Base):
    """User model for authentication and profile management."""
    
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Basic user information
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Authentication
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Fyers API credentials (encrypted)
    fyers_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fyers_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fyers_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # User preferences
    risk_tolerance: Mapped[str] = mapped_column(String(50), default="medium", nullable=False)  # low, medium, high
    max_position_size: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_daily_loss: Mapped[Optional[float]] = mapped_column(nullable=True)
    notification_preferences: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    strategies = relationship("Strategy", back_populates="user", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"
    
    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self.is_active and self.is_verified
    
    def has_fyers_credentials(self) -> bool:
        """Check if user has valid Fyers API credentials."""
        return (
            self.fyers_access_token is not None and
            self.fyers_refresh_token is not None and
            self.fyers_token_expires_at is not None and
            self.fyers_token_expires_at > datetime.utcnow()
        )
