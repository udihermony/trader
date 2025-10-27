"""
Trade execution engine for processing alerts and executing trades.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from loguru import logger

from app.models import User, Strategy, Trade, Alert, Portfolio, TradeStatus, OrderSide
from app.services.fyers_client import FyersClient, FyersAPIError
from app.redis_client import redis_client
from app.config import settings


class TradeExecutionError(Exception):
    """Custom exception for trade execution errors."""
    pass


class RiskManager:
    """Risk management for trade execution."""
    
    def __init__(self):
        self.max_position_size = settings.max_position_size
        self.max_daily_loss = settings.max_daily_loss
        self.max_daily_trades = settings.max_daily_trades
    
    async def check_risk_limits(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: int,
        price: float
    ) -> Tuple[bool, str]:
        """Check if trade violates risk limits."""
        try:
            # Check daily trade count
            today = datetime.utcnow().date()
            daily_trades_query = select(Trade).where(
                Trade.user_id == user_id,
                Trade.created_at >= today,
                Trade.status.in_([TradeStatus.FILLED, TradeStatus.PARTIALLY_FILLED])
            )
            daily_trades_result = await db.execute(daily_trades_query)
            daily_trades = daily_trades_result.scalars().all()
            
            if len(daily_trades) >= self.max_daily_trades:
                return False, f"Daily trade limit exceeded ({self.max_daily_trades})"
            
            # Check daily loss
            daily_loss = sum(
                trade.net_pnl or 0 for trade in daily_trades 
                if trade.net_pnl and trade.net_pnl < 0
            )
            
            if abs(daily_loss) >= self.max_daily_loss:
                return False, f"Daily loss limit exceeded ({self.max_daily_loss})"
            
            # Check position size
            trade_value = quantity * price
            if trade_value > self.max_position_size:
                return False, f"Position size exceeds limit ({self.max_position_size})"
            
            # Check existing position
            portfolio_query = select(Portfolio).where(
                Portfolio.user_id == user_id,
                Portfolio.symbol == symbol
            )
            portfolio_result = await db.execute(portfolio_query)
            portfolio = portfolio_result.scalar_one_or_none()
            
            if portfolio:
                new_position_size = abs(portfolio.quantity + (quantity if side.upper() == "BUY" else -quantity))
                if new_position_size * price > self.max_position_size:
                    return False, f"Total position size would exceed limit"
            
            return True, "Risk checks passed"
            
        except Exception as e:
            logger.error(f"Risk check failed: {e}")
            return False, f"Risk check error: {e}"


class TradeEngine:
    """Main trade execution engine."""
    
    def __init__(self):
        self.risk_manager = RiskManager()
        self._fyers_clients: Dict[uuid.UUID, FyersClient] = {}
    
    def _get_fyers_client(self, user: User) -> FyersClient:
        """Get or create Fyers client for user."""
        if user.id not in self._fyers_clients:
            self._fyers_clients[user.id] = FyersClient(user.fyers_access_token)
        return self._fyers_clients[user.id]
    
    async def process_alert(self, alert_id: uuid.UUID, db: AsyncSession) -> bool:
        """Process a trading alert and execute trades."""
        try:
            # Get alert
            alert_query = select(Alert).where(Alert.id == alert_id)
            alert_result = await db.execute(alert_query)
            alert = alert_result.scalar_one_or_none()
            
            if not alert:
                logger.error(f"Alert {alert_id} not found")
                return False
            
            if alert.is_processed:
                logger.warning(f"Alert {alert_id} already processed")
                return True
            
            # Check if this is a scan alert (informational only, no trade execution)
            if alert.metadata.get("is_scan_alert"):
                logger.info(f"Alert {alert_id} is a scan alert, skipping trade processing")
                alert.mark_as_ignored("Scan alert - informational only")
                await db.commit()
                return True
            
            # Mark alert as processing
            alert.mark_as_processing()
            await db.commit()
            
            # Get user
            user_query = select(User).where(User.id == alert.user_id)
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user:
                alert.mark_as_failed("User not found")
                await db.commit()
                return False
            
            if not user.has_fyers_credentials():
                alert.mark_as_failed("User has no valid Fyers credentials")
                await db.commit()
                return False
            
            # Find matching strategies
            strategies_query = select(Strategy).where(
                Strategy.user_id == user.id,
                Strategy.is_active == True
            )
            strategies_result = await db.execute(strategies_query)
            strategies = strategies_result.scalars().all()
            
            if not strategies:
                alert.mark_as_ignored("No active strategies found")
                await db.commit()
                return True
            
            # Process each matching strategy
            trades_executed = 0
            for strategy in strategies:
                if await self._should_execute_trade(alert, strategy):
                    success = await self._execute_trade(alert, strategy, user, db)
                    if success:
                        trades_executed += 1
            
            if trades_executed > 0:
                alert.mark_as_processed()
                logger.info(f"Successfully processed alert {alert_id}, executed {trades_executed} trades")
            else:
                alert.mark_as_ignored("No trades executed")
            
            await db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to process alert {alert_id}: {e}")
            try:
                alert.mark_as_failed(str(e))
                await db.commit()
            except:
                pass
            return False
    
    async def _should_execute_trade(self, alert: Alert, strategy: Strategy) -> bool:
        """Check if trade should be executed for this strategy."""
        try:
            # Check if alert type matches strategy
            if alert.alert_type.value not in ["buy", "sell"]:
                return False
            
            # Check strategy parameters
            if strategy.is_paper_trading:
                logger.info(f"Strategy {strategy.id} is in paper trading mode")
                return True
            
            # Check market hours (for live trading)
            fyers_client = FyersClient()
            try:
                is_market_open = await fyers_client.is_market_open()
                if not is_market_open:
                    logger.info("Market is closed, skipping live trade")
                    return False
            except Exception as e:
                logger.warning(f"Could not check market status: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking trade execution: {e}")
            return False
    
    async def _execute_trade(
        self,
        alert: Alert,
        strategy: Strategy,
        user: User,
        db: AsyncSession
    ) -> bool:
        """Execute a trade based on alert and strategy."""
        try:
            # Get Fyers client
            fyers_client = self._get_fyers_client(user)
            
            # Calculate position size
            quantity = await self._calculate_position_size(alert, strategy, user, db)
            if quantity <= 0:
                logger.warning(f"Invalid quantity calculated: {quantity}")
                return False
            
            # Check risk limits
            current_price = await fyers_client.get_current_price(alert.symbol)
            if not current_price:
                logger.error(f"Could not get current price for {alert.symbol}")
                return False
            
            risk_ok, risk_message = await self.risk_manager.check_risk_limits(
                db, user.id, alert.symbol, alert.alert_type.value, quantity, current_price
            )
            
            if not risk_ok:
                logger.warning(f"Risk check failed: {risk_message}")
                return False
            
            # Create trade record
            trade = Trade(
                user_id=user.id,
                strategy_id=strategy.id,
                alert_id=alert.id,
                symbol=alert.symbol,
                exchange=alert.exchange,
                side=OrderSide.BUY if alert.alert_type.value == "buy" else OrderSide.SELL,
                order_type="market",  # Default to market order
                quantity=quantity,
                price=current_price,
                status=TradeStatus.PENDING,
                created_at=datetime.utcnow()
            )
            
            db.add(trade)
            await db.flush()  # Get trade ID
            
            # Execute order
            if strategy.is_paper_trading:
                success = await self._execute_paper_trade(trade, fyers_client)
            else:
                success = await self._execute_live_trade(trade, fyers_client)
            
            if success:
                trade.status = TradeStatus.SUBMITTED
                trade.submitted_at = datetime.utcnow()
                
                # Update strategy metrics
                strategy.total_trades += 1
                strategy.last_executed_at = datetime.utcnow()
                
                logger.info(f"Successfully executed trade {trade.id}")
            else:
                trade.status = TradeStatus.FAILED
                logger.error(f"Failed to execute trade {trade.id}")
            
            await db.commit()
            return success
            
        except Exception as e:
            logger.error(f"Failed to execute trade: {e}")
            return False
    
    async def _calculate_position_size(
        self,
        alert: Alert,
        strategy: Strategy,
        user: User,
        db: AsyncSession
    ) -> int:
        """Calculate position size based on strategy rules."""
        try:
            # Get current price
            fyers_client = self._get_fyers_client(user)
            current_price = await fyers_client.get_current_price(alert.symbol)
            
            if not current_price:
                return 0
            
            # Get available funds
            funds_data = await fyers_client.get_funds()
            available_funds = funds_data.get("data", {}).get("fund_limit", 0)
            
            # Calculate position size based on strategy rules
            position_sizing_rules = strategy.position_sizing_rules
            
            if "fixed_amount" in position_sizing_rules:
                amount = position_sizing_rules["fixed_amount"]
                quantity = int(amount / current_price)
            elif "percentage_of_capital" in position_sizing_rules:
                percentage = position_sizing_rules["percentage_of_capital"]
                amount = available_funds * (percentage / 100)
                quantity = int(amount / current_price)
            elif "fixed_quantity" in position_sizing_rules:
                quantity = position_sizing_rules["fixed_quantity"]
            else:
                # Default: 1% of available funds
                amount = available_funds * 0.01
                quantity = int(amount / current_price)
            
            # Apply strategy limits
            if strategy.max_position_size:
                max_quantity = int(strategy.max_position_size / current_price)
                quantity = min(quantity, max_quantity)
            
            # Ensure minimum quantity
            quantity = max(quantity, 1)
            
            return quantity
            
        except Exception as e:
            logger.error(f"Failed to calculate position size: {e}")
            return 0
    
    async def _execute_paper_trade(self, trade: Trade, fyers_client: FyersClient) -> bool:
        """Execute a paper trade (simulation)."""
        try:
            # Simulate order execution
            await asyncio.sleep(0.1)  # Simulate network delay
            
            # Update trade with simulated execution
            trade.update_execution(
                filled_qty=trade.quantity,
                avg_price=trade.price,
                fyers_status="filled"
            )
            
            logger.info(f"Paper trade executed: {trade.symbol} {trade.side} {trade.quantity} @ {trade.price}")
            return True
            
        except Exception as e:
            logger.error(f"Paper trade execution failed: {e}")
            return False
    
    async def _execute_live_trade(self, trade: Trade, fyers_client: FyersClient) -> bool:
        """Execute a live trade via Fyers API."""
        try:
            # Place order
            if trade.order_type == "market":
                order_response = await fyers_client.place_market_order(
                    symbol=trade.symbol,
                    side=trade.side.value,
                    quantity=trade.quantity
                )
            elif trade.order_type == "limit":
                order_response = await fyers_client.place_limit_order(
                    symbol=trade.symbol,
                    side=trade.side.value,
                    quantity=trade.quantity,
                    price=trade.price
                )
            else:
                logger.error(f"Unsupported order type: {trade.order_type}")
                return False
            
            # Update trade with order details
            if order_response.get("data"):
                order_data = order_response["data"]
                trade.fyers_order_id = order_data.get("id")
                trade.fyers_status = order_data.get("status")
                trade.fyers_message = order_response.get("message")
                
                logger.info(f"Live order placed: {trade.fyers_order_id}")
                return True
            else:
                logger.error(f"Order placement failed: {order_response}")
                return False
                
        except FyersAPIError as e:
            logger.error(f"Fyers API error in live trade: {e}")
            return False
        except Exception as e:
            logger.error(f"Live trade execution failed: {e}")
            return False
    
    async def update_trade_status(self, trade_id: uuid.UUID, db: AsyncSession) -> bool:
        """Update trade status from Fyers API."""
        try:
            # Get trade
            trade_query = select(Trade).where(Trade.id == trade_id)
            trade_result = await db.execute(trade_query)
            trade = trade_result.scalar_one_or_none()
            
            if not trade or not trade.fyers_order_id:
                return False
            
            # Get user and Fyers client
            user_query = select(User).where(User.id == trade.user_id)
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user:
                return False
            
            fyers_client = self._get_fyers_client(user)
            
            # Get order status from Fyers
            order_data = await fyers_client.get_orders(trade.fyers_order_id)
            
            if order_data.get("data"):
                order_info = order_data["data"]
                trade.fyers_status = order_info.get("status")
                
                # Update trade status based on Fyers status
                fyers_status = order_info.get("status", "").lower()
                if fyers_status == "filled":
                    trade.status = TradeStatus.FILLED
                    trade.filled_at = datetime.utcnow()
                    trade.filled_quantity = order_info.get("filledQty", trade.quantity)
                    trade.average_price = order_info.get("avgPrice", trade.price)
                elif fyers_status == "cancelled":
                    trade.status = TradeStatus.CANCELLED
                    trade.cancelled_at = datetime.utcnow()
                elif fyers_status == "rejected":
                    trade.status = TradeStatus.REJECTED
                
                await db.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to update trade status: {e}")
            return False
    
    async def close_all_clients(self):
        """Close all Fyers clients."""
        for client in self._fyers_clients.values():
            await client.close()
        self._fyers_clients.clear()


# Global trade engine instance
trade_engine = TradeEngine()
