"""
Health check and monitoring routes.
"""

from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from loguru import logger

from app.db import get_db
from app.redis_client import redis_client
from app.services.fyers_client import FyersClient
from app.config import settings

router = APIRouter()


@router.get("/")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.app_version,
        "environment": settings.environment
    }


@router.get("/detailed")
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """Detailed health check with all dependencies."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.app_version,
        "environment": settings.environment,
        "checks": {}
    }
    
    # Database check
    try:
        await db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = {
            "status": "healthy",
            "message": "Database connection successful"
        }
    except Exception as e:
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
        health_status["status"] = "unhealthy"
    
    # Redis check
    try:
        redis_health = await redis_client.health_check()
        health_status["checks"]["redis"] = redis_health
        if redis_health["status"] != "healthy":
            health_status["status"] = "unhealthy"
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "message": f"Redis connection failed: {str(e)}"
        }
        health_status["status"] = "unhealthy"
    
    # Fyers API check
    try:
        fyers_client = FyersClient()
        fyers_health = await fyers_client.health_check()
        health_status["checks"]["fyers_api"] = fyers_health
        if fyers_health["status"] != "healthy":
            health_status["status"] = "unhealthy"
    except Exception as e:
        health_status["checks"]["fyers_api"] = {
            "status": "unhealthy",
            "message": f"Fyers API check failed: {str(e)}"
        }
        health_status["status"] = "unhealthy"
    
    return health_status


@router.get("/metrics")
async def get_metrics():
    """Get application metrics."""
    try:
        # Get Redis metrics
        redis_health = await redis_client.health_check()
        
        # Get queue sizes
        trade_queue_size = await redis_client.get_queue_size("trade_execution")
        alert_queue_size = await redis_client.get_queue_size("alert_processing")
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "redis": {
                "status": redis_health.get("status"),
                "uptime": redis_health.get("uptime"),
                "connected_clients": redis_health.get("connected_clients"),
                "used_memory": redis_health.get("used_memory")
            },
            "queues": {
                "trade_execution": trade_queue_size,
                "alert_processing": alert_queue_size
            },
            "application": {
                "version": settings.app_version,
                "environment": settings.environment,
                "debug": settings.debug
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@router.get("/status")
async def get_status():
    """Get application status."""
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": "N/A"  # Could be calculated if needed
    }
