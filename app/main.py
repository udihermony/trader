"""
Main FastAPI application entry point.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import time

from app.config import settings
from app.db import init_db, close_db
from app.redis_client import redis_client
from app.services.trade_engine import trade_engine
from app.routers import auth, chartlink, fyers, strategy, portfolio, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting AlgoTrader application...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized successfully")
        
        # Connect to Redis
        await redis_client.connect()
        logger.info("Redis connected successfully")
        
        # Start background tasks
        asyncio.create_task(background_task_processor())
        logger.info("Background task processor started")
        
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        logger.error(f"Application startup failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down AlgoTrader application...")
    
    try:
        # Close trade engine clients
        await trade_engine.close_all_clients()
        logger.info("Trade engine clients closed")
        
        # Disconnect from Redis
        await redis_client.disconnect()
        logger.info("Redis disconnected")
        
        # Close database connections
        await close_db()
        logger.info("Database connections closed")
        
        logger.info("Application shutdown completed successfully")
        
    except Exception as e:
        logger.error(f"Application shutdown error: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Comprehensive Algorithmic Trading Platform",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=settings.allowed_methods,
    allow_headers=settings.allowed_headers,
)

# Add trusted host middleware
if settings.environment == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # Configure with actual domains in production
    )


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "timestamp": time.time()
        }
    )


# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(chartlink.router, prefix="/api/v1/webhooks", tags=["Webhooks"])
app.include_router(fyers.router, prefix="/api/v1/fyers", tags=["Fyers API"])
app.include_router(strategy.router, prefix="/api/v1/strategies", tags=["Strategies"])
app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
app.include_router(health.router, prefix="/api/v1/health", tags=["Health"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "running"
    }


# Background task processor
async def background_task_processor():
    """Background task processor for handling queued tasks."""
    logger.info("Background task processor started")
    
    while True:
        try:
            # Process trade execution tasks
            task = await redis_client.dequeue_task("trade_execution", timeout=1)
            if task:
                await process_trade_task(task)
            
            # Process alert processing tasks
            task = await redis_client.dequeue_task("alert_processing", timeout=1)
            if task:
                await process_alert_task(task)
            
            # Small delay to prevent busy waiting
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error in background task processor: {e}")
            await asyncio.sleep(1)


async def process_trade_task(task_data: dict):
    """Process a trade execution task."""
    try:
        from app.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as db:
            trade_id = task_data["data"]["trade_id"]
            success = await trade_engine.update_trade_status(trade_id, db)
            
            if success:
                logger.info(f"Successfully processed trade task: {trade_id}")
            else:
                logger.warning(f"Failed to process trade task: {trade_id}")
                
    except Exception as e:
        logger.error(f"Error processing trade task: {e}")


async def process_alert_task(task_data: dict):
    """Process an alert processing task."""
    try:
        from app.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as db:
            alert_id = task_data["data"]["alert_id"]
            success = await trade_engine.process_alert(alert_id, db)
            
            if success:
                logger.info(f"Successfully processed alert task: {alert_id}")
            else:
                logger.warning(f"Failed to process alert task: {alert_id}")
                
    except Exception as e:
        logger.error(f"Error processing alert task: {e}")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
        log_level=settings.log_level.lower()
    )
