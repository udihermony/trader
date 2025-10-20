"""
Tests for the Fyers API client.
"""

import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.services.fyers_client import FyersClient, FyersAPIError


@pytest.mark.asyncio
async def test_fyers_client_initialization():
    """Test Fyers client initialization."""
    client = FyersClient("test_token")
    assert client.access_token == "test_token"
    assert client.base_url is not None
    assert client.app_id is not None


@pytest.mark.asyncio
async def test_fyers_client_auth_url():
    """Test Fyers authentication URL generation."""
    client = FyersClient()
    auth_url = await client.get_auth_url()
    
    assert "client_id" in auth_url
    assert "redirect_uri" in auth_url
    assert "response_type" in auth_url


@pytest.mark.asyncio
async def test_fyers_client_successful_request():
    """Test successful API request."""
    client = FyersClient("test_token")
    
    # Mock successful response
    mock_response = AsyncMock()
    mock_response.json.return_value = {"code": 200, "data": {"test": "data"}}
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        result = await client._make_request("GET", "/test")
        
        assert result["code"] == 200
        assert result["data"]["test"] == "data"


@pytest.mark.asyncio
async def test_fyers_client_api_error():
    """Test Fyers API error handling."""
    client = FyersClient("test_token")
    
    # Mock API error response
    mock_response = AsyncMock()
    mock_response.json.return_value = {"code": 400, "message": "Invalid request"}
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        with pytest.raises(FyersAPIError):
            await client._make_request("GET", "/test")


@pytest.mark.asyncio
async def test_fyers_client_http_error():
    """Test HTTP error handling."""
    client = FyersClient("test_token")
    
    with patch('httpx.AsyncClient.request', side_effect=httpx.HTTPError("Connection error")):
        with pytest.raises(FyersAPIError):
            await client._make_request("GET", "/test")


@pytest.mark.asyncio
async def test_fyers_client_get_profile():
    """Test get profile API call."""
    client = FyersClient("test_token")
    
    # Mock successful profile response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "fy_id": "test_user",
            "name": "Test User"
        }
    }
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        result = await client.get_profile()
        
        assert result["code"] == 200
        assert result["data"]["fy_id"] == "test_user"


@pytest.mark.asyncio
async def test_fyers_client_get_funds():
    """Test get funds API call."""
    client = FyersClient("test_token")
    
    # Mock successful funds response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "fund_limit": 100000,
            "utilized_amount": 5000
        }
    }
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        result = await client.get_funds()
        
        assert result["code"] == 200
        assert result["data"]["fund_limit"] == 100000


@pytest.mark.asyncio
async def test_fyers_client_place_market_order():
    """Test place market order API call."""
    client = FyersClient("test_token")
    
    # Mock successful order response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "id": "order_123",
            "status": "submitted"
        },
        "message": "Order placed successfully"
    }
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        result = await client.place_market_order(
            symbol="NSE:RELIANCE",
            side="BUY",
            quantity=10
        )
        
        assert result["code"] == 200
        assert result["data"]["id"] == "order_123"


@pytest.mark.asyncio
async def test_fyers_client_place_limit_order():
    """Test place limit order API call."""
    client = FyersClient("test_token")
    
    # Mock successful order response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "id": "order_456",
            "status": "submitted"
        },
        "message": "Order placed successfully"
    }
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        result = await client.place_limit_order(
            symbol="NSE:RELIANCE",
            side="BUY",
            quantity=10,
            price=2500.0
        )
        
        assert result["code"] == 200
        assert result["data"]["id"] == "order_456"


@pytest.mark.asyncio
async def test_fyers_client_get_quotes():
    """Test get quotes API call."""
    client = FyersClient("test_token")
    
    # Mock successful quotes response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "NSE:RELIANCE": {
                "v": {
                    "lp": 2500.50,
                    "ch": 25.30,
                    "chp": 1.02
                }
            }
        }
    }
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        result = await client.get_quotes(["NSE:RELIANCE"])
        
        assert result["code"] == 200
        assert "NSE:RELIANCE" in result["data"]
        assert result["data"]["NSE:RELIANCE"]["v"]["lp"] == 2500.50


@pytest.mark.asyncio
async def test_fyers_client_get_current_price():
    """Test get current price helper method."""
    client = FyersClient("test_token")
    
    # Mock successful quotes response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "NSE:RELIANCE": {
                "v": {
                    "lp": 2500.50
                }
            }
        }
    }
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        price = await client.get_current_price("NSE:RELIANCE")
        
        assert price == 2500.50


@pytest.mark.asyncio
async def test_fyers_client_get_current_price_error():
    """Test get current price error handling."""
    client = FyersClient("test_token")
    
    with patch('httpx.AsyncClient.request', side_effect=httpx.HTTPError("Connection error")):
        price = await client.get_current_price("NSE:RELIANCE")
        
        assert price is None


@pytest.mark.asyncio
async def test_fyers_client_health_check():
    """Test health check method."""
    client = FyersClient("test_token")
    
    # Mock successful profile response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "fy_id": "test_user"
        }
    }
    mock_response.raise_for_status.return_value = None
    
    with patch('httpx.AsyncClient.request', return_value=mock_response):
        health = await client.health_check()
        
        assert health["status"] == "healthy"
        assert health["api_connected"] is True
        assert health["user_id"] == "test_user"


@pytest.mark.asyncio
async def test_fyers_client_health_check_failure():
    """Test health check failure."""
    client = FyersClient("test_token")
    
    with patch('httpx.AsyncClient.request', side_effect=httpx.HTTPError("Connection error")):
        health = await client.health_check()
        
        assert health["status"] == "unhealthy"
        assert health["api_connected"] is False
        assert "error" in health


@pytest.mark.asyncio
async def test_fyers_client_close():
    """Test client close method."""
    client = FyersClient("test_token")
    
    with patch.object(client._client, 'aclose') as mock_close:
        await client.close()
        mock_close.assert_called_once()
