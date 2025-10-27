"""
Chartlink webhook endpoint for receiving trading signals.
"""

import uuid
import hashlib
import hmac
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Request, HTTPException, status, Depends, Body
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
    """Trading signal format (BUY/SELL order)"""
    symbol: str = Field(..., description="Trading symbol (e.g., NSE:RELIANCE)")
    action: str = Field(..., description="Trading action (BUY, SELL, HOLD)")
    price: Optional[float] = Field(None, description="Signal price")
    quantity: Optional[int] = Field(None, description="Suggested quantity")
    message: Optional[str] = Field(None, description="Signal message")
    timestamp: Optional[str] = Field(None, description="Signal timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class ChartlinkScanPayload(BaseModel):
    """Scan alert format (multiple stocks with trigger prices)"""
    stocks: str = Field(..., description="Comma-separated stock symbols")
    trigger_prices: Optional[str] = Field(None, description="Comma-separated trigger prices")
    triggered_at: Optional[str] = Field(None, description="Time of trigger")
    scan_name: Optional[str] = Field(None, description="Name of the scan")
    scan_url: Optional[str] = Field(None, description="Scan URL")
    alert_name: Optional[str] = Field(None, description="Alert name")
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
    unique_id: Optional[str] = Field(None, description="Unique alert ID")
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


def is_chartlink_scan_payload(data: Dict[str, Any]) -> bool:
    """Check if payload is a Chartlink scan alert."""
    return bool(data and "stocks" in data)


def parse_chartlink_scan(scan_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse Chartlink scan payload into individual stocks."""
    if not scan_data or not scan_data.get("stocks"):
        return []
    
    stocks_str = scan_data.get("stocks", "")
    prices_str = scan_data.get("trigger_prices", "")
    
    stocks = [s.strip() for s in stocks_str.split(",") if s.strip()]
    prices = []
    
    if prices_str:
        try:
            prices = [float(p.strip()) if p.strip() else None for p in prices_str.split(",")]
        except (ValueError, AttributeError):
            prices = []
    
    # Match stocks with their prices
    items = []
    for i, stock in enumerate(stocks):
        items.append({
            "symbol": stock,
            "trigger_price": prices[i] if i < len(prices) else None
        })
    
    return items


def generate_idempotency_key(scan_data: Dict[str, Any]) -> str:
    """Generate idempotency key for Chartlink scan alerts."""
    if scan_data.get("unique_id"):
        return f"chartlink_{scan_data['unique_id']}"
    
    # Use stable key for scans
    if scan_data.get("stocks") and scan_data.get("triggered_at") and scan_data.get("scan_name"):
        base = f"{scan_data['scan_name']}|{scan_data['triggered_at']}|{scan_data['stocks']}"
        key_hash = hashlib.sha256(base.encode()).hexdigest()
        return f"chartlink_scan_{key_hash[:16]}"
    
    # Fallback to hash of entire payload
    payload_str = json.dumps(scan_data, sort_keys=True)
    key_hash = hashlib.sha256(payload_str.encode()).hexdigest()
    return f"chartlink_{key_hash[:16]}"


@router.post("/chartlink", response_model=WebhookResponse)
async def receive_chartlink_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Receive trading signals and scans from Chartlink webhook."""
    try:
        # Get raw request body
        body_bytes = await request.body()
        body = json.loads(body_bytes)
        
        # Verify webhook signature if secret is configured
        if settings.chartlink_webhook_secret:
            signature = request.headers.get("X-Chartlink-Signature", "")
            if not verify_webhook_signature(body_bytes, signature, settings.chartlink_webhook_secret):
                logger.warning("Invalid webhook signature")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
        
        # Check if this is a scan payload
        if is_chartlink_scan_payload(body):
            return await _handle_scan_payload(body, body_bytes, db)
        else:
            return await _handle_signal_payload(body, db)
            
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Chartlink webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )


async def _handle_scan_payload(
    scan_data: Dict[str, Any],
    body_bytes: bytes,
    db: AsyncSession
) -> WebhookResponse:
    """Handle Chartlink scan alert (no trading fields)."""
    try:
        # Parse scan items
        items = parse_chartlink_scan(scan_data)
        
        logger.info(f"Received Chartlink scan alert: {scan_data.get('scan_name')}, "
                   f"triggered_at: {scan_data.get('triggered_at')}, "
                   f"stocks count: {len(items)}")
        
        # Get all active users
        users_query = select(User).where(User.is_active == True)
        users_result = await db.execute(users_query)
        users = users_result.scalars().all()
        
        if not users:
            logger.warning("No active users found for scan processing")
            return WebhookResponse(
                success=False,
                message="No active users found"
            )
        
        # Generate idempotency key
        external_id = generate_idempotency_key(scan_data)
        
        # Get first stock for symbol field
        first_symbol = items[0]["symbol"] if items else "UNKNOWN"
        exchange, symbol = parse_symbol(first_symbol)
        
        alert_ids = []
        for user in users:
            # Store scan as informational alert (not for trade execution)
            alert = Alert(
                user_id=user.id,
                symbol=symbol,
                exchange=exchange,
                alert_type=AlertType.HOLD,  # Scan alerts don't have explicit action
                source=AlertSource.CHARTLINK,
                price=float(items[0]["trigger_price"]) if items and items[0]["trigger_price"] else None,
                quantity=None,  # No quantity for scans
                message=scan_data.get("alert_name") or scan_data.get("scan_name"),
                metadata={
                    "is_scan_alert": True,
                    "scan_name": scan_data.get("scan_name"),
                    "triggered_at": scan_data.get("triggered_at"),
                    "scan_url": scan_data.get("scan_url"),
                    "webhook_url": scan_data.get("webhook_url"),
                    "stocks": items,
                    "raw_payload": scan_data,
                    "stocks_count": len(items)
                },
                external_id=external_id,
                external_source="chartlink_scan",
                status=AlertStatus.RECEIVED,  # Received, not processed
                created_at=datetime.utcnow()
            )
            
            db.add(alert)
            await db.flush()
            alert_ids.append(alert.id)
            
            # Don't enqueue scan alerts for trade processing
            # They're informational only
        
        await db.commit()
        
        logger.info(f"Stored Chartlink scan alert, created {len(alert_ids)} alerts for {len(items)} stocks")
        
        return WebhookResponse(
            success=True,
            message=f"Scan alert stored successfully, {len(items)} stocks",
            alert_id=alert_ids[0] if alert_ids else None
        )
        
    except Exception as e:
        logger.error(f"Error handling scan payload: {e}")
        raise


async def _handle_signal_payload(
    signal_data: Dict[str, Any],
    db: AsyncSession
) -> WebhookResponse:
    """Handle Chartlink trading signal (BUY/SELL order)."""
    try:
        # Validate and parse signal
        if not signal_data.get("symbol") or not signal_data.get("action"):
            return WebhookResponse(
                success=False,
                message="Missing required fields: symbol and action"
            )
        
        symbol = signal_data["symbol"]
        action = signal_data["action"]
        price = signal_data.get("price")
        quantity = signal_data.get("quantity")
        
        # Parse symbol
        exchange, symbol_name = parse_symbol(symbol)
        
        # Map action to alert type
        alert_type = map_action_to_alert_type(action)
        
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
                symbol=symbol_name,
                exchange=exchange,
                alert_type=alert_type,
                source=AlertSource.CHARTLINK,
                price=price,
                quantity=quantity,
                message=signal_data.get("message"),
                metadata={
                    "original_symbol": symbol,
                    "timestamp": signal_data.get("timestamp"),
                    "raw_payload": signal_data,
                    **signal_data.get("metadata", {})
                },
                external_id=f"chartlink_{datetime.utcnow().timestamp()}",
                external_source="chartlink",
                status=AlertStatus.RECEIVED,
                created_at=datetime.utcnow()
            )
            
            db.add(alert)
            await db.flush()
            alert_ids.append(alert.id)
            
            # Enqueue alert for trade processing
            await redis_client.enqueue_task(
                "alert_processing",
                {"alert_id": str(alert.id)},
                priority=1  # High priority for real-time signals
            )
        
        await db.commit()
        
        logger.info(f"Received Chartlink signal: {symbol} {action}, created {len(alert_ids)} alerts")
        
        return WebhookResponse(
            success=True,
            message=f"Signal processed successfully, created {len(alert_ids)} alerts",
            alert_id=alert_ids[0] if alert_ids else None
        )
        
    except Exception as e:
        logger.error(f"Error handling signal payload: {e}")
        raise


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


@router.post("/test-scan", response_model=WebhookResponse)
async def test_scan(
    scan_data: ChartlinkScanPayload,
    db: AsyncSession = Depends(get_db)
):
    """Test endpoint for creating sample scan alerts."""
    try:
        # Convert Pydantic model to dict
        body = scan_data.model_dump()
        
        # Create a minimal body_bytes for the handler
        body_bytes = json.dumps(body).encode()
        
        # Use the same handler as the webhook
        return await _handle_scan_payload(body, body_bytes, db)
        
    except Exception as e:
        logger.error(f"Error creating test scan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create test scan"
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
                    "processed_at": alert.processed_at,
                    "metadata": alert.metadata
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