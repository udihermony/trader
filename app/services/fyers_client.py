"""
Fyers API client for trading operations and market data.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlencode

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class FyersAPIError(Exception):
    """Custom exception for Fyers API errors."""
    pass


class FyersClient:
    """Async Fyers API client for trading operations."""
    
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.base_url = settings.fyers_base_url
        self.app_id = settings.fyers_app_id
        self.secret_key = settings.fyers_secret_key
        self.redirect_uri = settings.fyers_redirect_uri
        
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        
        return headers
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Fyers API with retry logic."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = await self._client.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                params=params
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Check for Fyers API errors
            if result.get("code") != 200:
                error_msg = result.get("message", "Unknown error")
                logger.error(f"Fyers API error: {error_msg}")
                raise FyersAPIError(f"API Error {result.get('code')}: {error_msg}")
            
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in Fyers API request: {e}")
            raise FyersAPIError(f"HTTP error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in Fyers API response: {e}")
            raise FyersAPIError(f"Invalid JSON response: {e}")
    
    async def get_auth_url(self) -> str:
        """Generate Fyers authentication URL."""
        auth_params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": "sample_state"
        }
        
        auth_url = f"https://api-t1.fyers.in/api/v3/generate-authcode"
        return f"{auth_url}?{urlencode(auth_params)}"
    
    async def get_access_token(self, auth_code: str) -> Dict[str, Any]:
        """Exchange auth code for access token."""
        data = {
            "client_id": self.app_id,
            "secret_key": self.secret_key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": "sample_state",
            "grant_type": "authorization_code",
            "code": auth_code
        }
        
        result = await self._make_request("POST", "/token", data=data)
        
        if "access_token" in result:
            self.access_token = result["access_token"]
            logger.info("Successfully obtained Fyers access token")
        
        return result
    
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        data = {
            "client_id": self.app_id,
            "secret_key": self.secret_key,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        
        result = await self._make_request("POST", "/token", data=data)
        
        if "access_token" in result:
            self.access_token = result["access_token"]
            logger.info("Successfully refreshed Fyers access token")
        
        return result
    
    async def get_profile(self) -> Dict[str, Any]:
        """Get user profile information."""
        return await self._make_request("GET", "/profile")
    
    async def get_funds(self) -> Dict[str, Any]:
        """Get available funds."""
        return await self._make_request("GET", "/funds")
    
    async def get_holdings(self) -> Dict[str, Any]:
        """Get current holdings."""
        return await self._make_request("GET", "/holdings")
    
    async def get_positions(self) -> Dict[str, Any]:
        """Get current positions."""
        return await self._make_request("GET", "/positions")
    
    async def place_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Place a new order."""
        return await self._make_request("POST", "/orders", data=order_data)
    
    async def modify_order(self, order_id: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Modify an existing order."""
        return await self._make_request("PUT", f"/orders/{order_id}", data=order_data)
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order."""
        return await self._make_request("DELETE", f"/orders/{order_id}")
    
    async def get_orders(self, order_id: Optional[str] = None) -> Dict[str, Any]:
        """Get order details."""
        endpoint = f"/orders/{order_id}" if order_id else "/orders"
        return await self._make_request("GET", endpoint)
    
    async def get_order_history(self, order_id: str) -> Dict[str, Any]:
        """Get order history for a specific order."""
        return await self._make_request("GET", f"/orders/{order_id}/history")
    
    async def get_tradebook(self) -> Dict[str, Any]:
        """Get trade book."""
        return await self._make_request("GET", "/tradebook")
    
    async def get_market_status(self) -> Dict[str, Any]:
        """Get market status."""
        return await self._make_request("GET", "/market-status")
    
    async def get_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        """Get quotes for symbols."""
        params = {"symbols": ",".join(symbols)}
        return await self._make_request("GET", "/quotes", params=params)
    
    async def get_historical_data(
        self,
        symbol: str,
        resolution: str,
        date_format: int = 1,
        range_from: Optional[str] = None,
        range_to: Optional[str] = None,
        cont_flag: int = 1
    ) -> Dict[str, Any]:
        """Get historical data for a symbol."""
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": date_format,
            "cont_flag": cont_flag
        }
        
        if range_from:
            params["range_from"] = range_from
        if range_to:
            params["range_to"] = range_to
        
        return await self._make_request("GET", "/historical", params=params)
    
    # Helper methods for common trading operations
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        product_type: str = "INTRADAY"
    ) -> Dict[str, Any]:
        """Place a market order."""
        order_data = {
            "symbol": symbol,
            "qty": quantity,
            "type": 1,  # Market order
            "side": 1 if side.upper() == "BUY" else -1,
            "productType": product_type,
            "limitPrice": 0,
            "stopPrice": 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": "False"
        }
        
        return await self.place_order(order_data)
    
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        product_type: str = "INTRADAY"
    ) -> Dict[str, Any]:
        """Place a limit order."""
        order_data = {
            "symbol": symbol,
            "qty": quantity,
            "type": 2,  # Limit order
            "side": 1 if side.upper() == "BUY" else -1,
            "productType": product_type,
            "limitPrice": price,
            "stopPrice": 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": "False"
        }
        
        return await self.place_order(order_data)
    
    async def place_stop_loss_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        stop_price: float,
        product_type: str = "INTRADAY"
    ) -> Dict[str, Any]:
        """Place a stop loss order."""
        order_data = {
            "symbol": symbol,
            "qty": quantity,
            "type": 3,  # Stop loss order
            "side": 1 if side.upper() == "BUY" else -1,
            "productType": product_type,
            "limitPrice": 0,
            "stopPrice": stop_price,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": "False"
        }
        
        return await self.place_order(order_data)
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            quotes = await self.get_quotes([symbol])
            if quotes.get("data") and symbol in quotes["data"]:
                return quotes["data"][symbol]["v"]["lp"]  # Last price
            return None
        except Exception as e:
            logger.error(f"Failed to get current price for {symbol}: {e}")
            return None
    
    async def is_market_open(self) -> bool:
        """Check if market is currently open."""
        try:
            status = await self.get_market_status()
            return status.get("data", {}).get("is_open", False)
        except Exception as e:
            logger.error(f"Failed to check market status: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Fyers API."""
        try:
            profile = await self.get_profile()
            return {
                "status": "healthy",
                "api_connected": True,
                "user_id": profile.get("data", {}).get("fy_id"),
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Fyers API health check failed: {e}")
            return {
                "status": "unhealthy",
                "api_connected": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
