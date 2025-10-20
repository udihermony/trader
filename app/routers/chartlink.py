"""
Chartlink webhook endpoint for receiving trading signals.
"""

import uuid
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from loguru import logger

from app.db import get_db
from app.models import User, Alert, AlertType, AlertSource, AlertStatus
from app.config import settings
from app.redis_client import redis_client

router = APIRouter()
security = HTTPBearer()


# Pydantic models for webhook data
class ChartlinkSignal(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., NSE:RELIANCE)")
    action: str = Field(..., description="Trading action (BUY, SELL, HOLD)")
    price: Optional[float] = Field(None, description="Signal price")
    quantity: Optional[int] = Field(None, description="Suggested quantity")
    message: Optional[str] = Field(None, description="Signal message")
    timestamp: Optional[str] = Field(None, description="Signal timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class WebhookResponse(BaseModel):
    success: bool
    message: str
    alert_id: Optional[uuid.UUID] = None


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature."""
    try:
        expected_signature = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False


def parse_symbol(symbol: str) -> tuple[str, str]:
    """Parse symbol into exchange and symbol."""
    if ":" in symbol:
        exchange, symbol_name = symbol.split(":", 1)
        return exchange.upper(), symbol_name
    else:
        return "NSE", symbol  # Default to NSE


def map_action_to_alert_type(action: str) -> AlertType:
    """Map Chartlink action to AlertType."""
    action_mapping = {
        "BUY": AlertType.BUY,
        "SELL": AlertType.SELL,
        "HOLD": AlertType.HOLD,
        "STOP_LOSS": AlertType.STOP_LOSS,
        "TAKE_PROFIT": AlertType.TAKE_PROFIT
    }
    return action_mapping.get(action.upper(), AlertType.HOLD)


@router.post("/chartlink", response_model=WebhookResponse)
async def receive_chartlink_signal(
    request: Request,
    signal_data: ChartlinkSignal,
    db: AsyncSession = Depends(get_db)
):
    """Receive trading signals from Chartlink webhook."""
    try:
        # Get raw request body for signature verification
        body = await request.body()
        
        # Verify webhook signature if secret is configured
        if settings.chartlink_webhook_secret:
            signature = request.headers.get("X-Chartlink-Signature", "")
            if not verify_webhook_signature(body, signature, settings.chartlink_webhook_secret):
                logger.warning("Invalid webhook signature")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
        
        # Parse symbol
        exchange, symbol = parse_symbol(signal_data.symbol)
        
        # Map action to alert type
        alert_type = map_action_to_alert_type(signal_data.action)
        
        # For now, we'll create alerts for all users (in production, you might want to filter)
        # Get all active users
        users_query = select(User).where(User.is_active == True)
        users_result = await db.execute(users_query)
        users = users_result.scalars().all()
        
        if not users:
            logger.warning("No active users found for signal processing")
            return WebhookResponse(
                success=False,
                message="No active users found"
            )
        
        # Create alerts for each user
        alert_ids = []
        for user in users:
            alert = Alert(
                user_id=user.id,
                symbol=symbol,
                exchange=exchange,
                alert_type=alert_type,
                source=AlertSource.CHARTLINK,
                price=signal_data.price,
                quantity=signal_data.quantity,
                message=signal_data.message,
                metadata={
                    "original_symbol": signal_data.symbol,
                    "timestamp": signal_data.timestamp,
                    **signal_data.metadata
                },
                external_id=f"chartlink_{datetime.utcnow().timestamp()}",
                external_source="chartlink",
                status=AlertStatus.RECEIVED,
                created_at=datetime.utcnow()
            )
            
            db.add(alert)
            await db.flush()  # Get alert ID
            alert_ids.append(alert.id)
            
            # Enqueue alert for processing
            await redis_client.enqueue_task(
                "alert_processing",
                {"alert_id": str(alert.id)},
                priority=1  # High priority for real-time signals
            )
        
        await db.commit()
        
        logger.info(f"Received Chartlink signal: {signal_data.symbol} {signal_data.action}, created {len(alert_ids)} alerts")
        
        return WebhookResponse(
            success=True,
            message=f"Signal processed successfully, created {len(alert_ids)} alerts",
            alert_id=alert_ids[0] if alert_ids else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Chartlink webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook signal"
        )


@router.post("/test-signal", response_model=WebhookResponse)
async def test_signal(
    signal_data: ChartlinkSignal,
    db: AsyncSession = Depends(get_db)
):
    """Test endpoint for creating sample signals."""
    try:
        # Parse symbol
        exchange, symbol = parse_symbol(signal_data.symbol)
        
        # Map action to alert type
        alert_type = map_action_to_alert_type(signal_data.action)
        
        # Get first active user for testing
        users_query = select(User).where(User.is_active == True)
        users_result = await db.execute(users_query)
        user = users_result.scalar_one_or_none()
        
        if not user:
            return WebhookResponse(
                success=False,
                message="No active users found"
            )
        
        # Create test alert
        alert = Alert(
            user_id=user.id,
            symbol=symbol,
            exchange=exchange,
            alert_type=alert_type,
            source=AlertSource.MANUAL,
            price=signal_data.price,
            quantity=signal_data.quantity,
            message=f"Test signal: {signal_data.message}",
            metadata={
                "test": True,
                "original_symbol": signal_data.symbol,
                **signal_data.metadata
            },
            external_id=f"test_{datetime.utcnow().timestamp()}",
            external_source="test",
            status=AlertStatus.RECEIVED,
            created_at=datetime.utcnow()
        )
        
        db.add(alert)
        await db.flush()
        
        # Enqueue for processing
        await redis_client.enqueue_task(
            "alert_processing",
            {"alert_id": str(alert.id)},
            priority=1
        )
        
        await db.commit()
        
        logger.info(f"Created test signal: {signal_data.symbol} {signal_data.action}")
        
        return WebhookResponse(
            success=True,
            message="Test signal created successfully",
            alert_id=alert.id
        )
        
    except Exception as e:
        logger.error(f"Error creating test signal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create test signal"
        )


@router.get("/alerts/recent")
async def get_recent_alerts(
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Get recent alerts for monitoring."""
    try:
        alerts_query = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
        alerts_result = await db.execute(alerts_query)
        alerts = alerts_result.scalars().all()
        
        return {
            "alerts": [
                {
                    "id": alert.id,
                    "symbol": alert.symbol,
                    "exchange": alert.exchange,
                    "alert_type": alert.alert_type.value,
                    "source": alert.source.value,
                    "status": alert.status.value,
                    "price": alert.price,
                    "quantity": alert.quantity,
                    "message": alert.message,
                    "created_at": alert.created_at,
                    "processed_at": alert.processed_at
                }
                for alert in alerts
            ],
            "total": len(alerts)
        }
        
    except Exception as e:
        logger.error(f"Error fetching recent alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch alerts"
        )
