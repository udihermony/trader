"""
Fyers API integration routes.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from loguru import logger

from app.db import get_db
from app.models import User, Trade, TradeStatus
from app.services.fyers_client import FyersClient, FyersAPIError
from app.routers.auth import get_current_active_user

router = APIRouter()


# Pydantic models
class OrderRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Order side (BUY/SELL)")
    quantity: int = Field(..., description="Order quantity")
    order_type: str = Field("market", description="Order type (market/limit)")
    price: Optional[float] = Field(None, description="Limit price for limit orders")
    product_type: str = Field("INTRADAY", description="Product type")


class OrderResponse(BaseModel):
    success: bool
    message: str
    order_id: Optional[str] = None
    trade_id: Optional[uuid.UUID] = None


class PositionResponse(BaseModel):
    symbol: str
    quantity: int
    average_price: float
    current_price: float
    pnl: float
    pnl_percentage: float


class FundsResponse(BaseModel):
    available_funds: float
    utilized_funds: float
    total_funds: float


@router.get("/profile")
async def get_fyers_profile(current_user: User = Depends(get_current_active_user)):
    """Get Fyers user profile."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        fyers_client = FyersClient(current_user.fyers_access_token)
        profile = await fyers_client.get_profile()
        
        return profile
        
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting Fyers profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get profile"
        )


@router.get("/funds", response_model=FundsResponse)
async def get_funds(current_user: User = Depends(get_current_active_user)):
    """Get available funds."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        fyers_client = FyersClient(current_user.fyers_access_token)
        funds_data = await fyers_client.get_funds()
        
        if funds_data.get("data"):
            data = funds_data["data"]
            return FundsResponse(
                available_funds=data.get("fund_limit", 0),
                utilized_funds=data.get("utilized_amount", 0),
                total_funds=data.get("fund_limit", 0) + data.get("utilized_amount", 0)
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get funds data"
            )
            
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting funds: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get funds"
        )


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(current_user: User = Depends(get_current_active_user)):
    """Get current positions."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        fyers_client = FyersClient(current_user.fyers_access_token)
        positions_data = await fyers_client.get_positions()
        
        positions = []
        if positions_data.get("data"):
            for position in positions_data["data"]:
                positions.append(PositionResponse(
                    symbol=position.get("symbol", ""),
                    quantity=position.get("qty", 0),
                    average_price=position.get("avgPrice", 0),
                    current_price=position.get("currentPrice", 0),
                    pnl=position.get("pl", 0),
                    pnl_percentage=position.get("plPercent", 0)
                ))
        
        return positions
        
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get positions"
        )


@router.get("/holdings")
async def get_holdings(current_user: User = Depends(get_current_active_user)):
    """Get current holdings."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        fyers_client = FyersClient(current_user.fyers_access_token)
        holdings = await fyers_client.get_holdings()
        
        return holdings
        
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting holdings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get holdings"
        )


@router.post("/orders", response_model=OrderResponse)
async def place_order(
    order_request: OrderRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Place a new order."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        fyers_client = FyersClient(current_user.fyers_access_token)
        
        # Place order based on type
        if order_request.order_type.lower() == "market":
            order_response = await fyers_client.place_market_order(
                symbol=order_request.symbol,
                side=order_request.side,
                quantity=order_request.quantity,
                product_type=order_request.product_type
            )
        elif order_request.order_type.lower() == "limit":
            if not order_request.price:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Price is required for limit orders"
                )
            order_response = await fyers_client.place_limit_order(
                symbol=order_request.symbol,
                side=order_request.side,
                quantity=order_request.quantity,
                price=order_request.price,
                product_type=order_request.product_type
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid order type"
            )
        
        # Create trade record
        trade = Trade(
            user_id=current_user.id,
            symbol=order_request.symbol,
            exchange="NSE",  # Default exchange
            side=order_request.side.upper(),
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            price=order_request.price,
            status=TradeStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        
        if order_response.get("data"):
            order_data = order_response["data"]
            trade.fyers_order_id = order_data.get("id")
            trade.fyers_status = order_data.get("status")
            trade.fyers_message = order_response.get("message")
        
        db.add(trade)
        await db.commit()
        await db.refresh(trade)
        
        logger.info(f"Order placed: {order_request.symbol} {order_request.side} {order_request.quantity}")
        
        return OrderResponse(
            success=True,
            message="Order placed successfully",
            order_id=trade.fyers_order_id,
            trade_id=trade.id
        )
        
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to place order"
        )


@router.get("/orders")
async def get_orders(
    order_id: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
):
    """Get order details."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        fyers_client = FyersClient(current_user.fyers_access_token)
        orders = await fyers_client.get_orders(order_id)
        
        return orders
        
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get orders"
        )


@router.delete("/orders/{order_id}")
async def cancel_order(
    order_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Cancel an order."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        fyers_client = FyersClient(current_user.fyers_access_token)
        response = await fyers_client.cancel_order(order_id)
        
        logger.info(f"Order cancelled: {order_id}")
        
        return response
        
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel order"
        )


@router.get("/quotes")
async def get_quotes(
    symbols: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get quotes for symbols."""
    try:
        if not current_user.has_fyers_credentials():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid Fyers credentials found"
            )
        
        symbol_list = [s.strip() for s in symbols.split(",")]
        fyers_client = FyersClient(current_user.fyers_access_token)
        quotes = await fyers_client.get_quotes(symbol_list)
        
        return quotes
        
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting quotes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get quotes"
        )


@router.get("/market-status")
async def get_market_status(current_user: User = Depends(get_current_active_user)):
    """Get market status."""
    try:
        fyers_client = FyersClient()
        status_data = await fyers_client.get_market_status()
        
        return status_data
        
    except FyersAPIError as e:
        logger.error(f"Fyers API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get market status"
        )
