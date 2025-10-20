"""
Comprehensive logging configuration with Loguru.
"""

import sys
import os
from pathlib import Path
from loguru import logger
from typing import Dict, Any

from app.config import settings


def setup_logging():
    """Configure Loguru logging with multiple handlers."""
    
    # Remove default handler
    logger.remove()
    
    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Console handler with colors
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # File handler for all logs
    logger.add(
        logs_dir / "app.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="1 day",
        retention="30 days",
        compression="zip",
        backtrace=True,
        diagnose=True
    )
    
    # Error file handler
    logger.add(
        logs_dir / "error.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="1 day",
        retention="90 days",
        compression="zip",
        backtrace=True,
        diagnose=True
    )
    
    # Trade execution logs
    logger.add(
        logs_dir / "trades.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="1 day",
        retention="365 days",  # Keep trade logs longer
        compression="zip",
        filter=lambda record: "trade" in record["message"].lower() or "order" in record["message"].lower()
    )
    
    # Webhook logs
    logger.add(
        logs_dir / "webhooks.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="1 day",
        retention="30 days",
        compression="zip",
        filter=lambda record: "webhook" in record["message"].lower() or "alert" in record["message"].lower()
    )
    
    # Performance logs
    logger.add(
        logs_dir / "performance.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="1 day",
        retention="30 days",
        compression="zip",
        filter=lambda record: "performance" in record["message"].lower() or "metrics" in record["message"].lower()
    )
    
    # Configure for production
    if settings.environment == "production":
        # Add CloudWatch handler if AWS credentials are available
        try:
            import boto3
            from botocore.exceptions import NoCredentialsError
            
            # Test AWS credentials
            boto3.client('logs', region_name=settings.aws_region)
            
            # CloudWatch handler
            logger.add(
                lambda msg: send_to_cloudwatch(msg),
                level="INFO",
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                filter=lambda record: record["level"].no >= 20  # INFO and above
            )
            
        except (NoCredentialsError, Exception) as e:
            logger.warning(f"CloudWatch logging not available: {e}")
    
    # Add custom log levels
    logger.level("TRADE", no=25, color="<blue>")
    logger.level("ALERT", no=26, color="<yellow>")
    logger.level("RISK", no=27, color="<red>")
    
    logger.info(f"Logging configured for {settings.environment} environment")
    logger.info(f"Log level: {settings.log_level}")
    logger.info(f"Logs directory: {logs_dir.absolute()}")


def send_to_cloudwatch(message: str):
    """Send log message to CloudWatch."""
    try:
        import boto3
        import json
        
        logs_client = boto3.client('logs', region_name=settings.aws_region)
        
        log_group = f"/alogtrader/{settings.environment}"
        log_stream = f"app-{os.getpid()}"
        
        # Create log group if it doesn't exist
        try:
            logs_client.create_log_group(logGroupName=log_group)
        except logs_client.exceptions.ResourceAlreadyExistsException:
            pass
        
        # Create log stream if it doesn't exist
        try:
            logs_client.create_log_stream(
                logGroupName=log_group,
                logStreamName=log_stream
            )
        except logs_client.exceptions.ResourceAlreadyExistsException:
            pass
        
        # Send log event
        logs_client.put_log_events(
            logGroupName=log_group,
            logStreamName=log_stream,
            logEvents=[
                {
                    'timestamp': int(message.split(' | ')[0].replace(':', '').replace('-', '').replace(' ', '')),
                    'message': message
                }
            ]
        )
        
    except Exception as e:
        # Fallback to file logging if CloudWatch fails
        logger.error(f"Failed to send log to CloudWatch: {e}")


class LoggerMixin:
    """Mixin class to add logging capabilities to any class."""
    
    @property
    def logger(self):
        """Get logger instance for this class."""
        return logger.bind(name=self.__class__.__name__)
    
    def log_trade(self, message: str, **kwargs):
        """Log trade-related message."""
        logger.bind(**kwargs).log("TRADE", message)
    
    def log_alert(self, message: str, **kwargs):
        """Log alert-related message."""
        logger.bind(**kwargs).log("ALERT", message)
    
    def log_risk(self, message: str, **kwargs):
        """Log risk-related message."""
        logger.bind(**kwargs).log("RISK", message)


def log_function_call(func):
    """Decorator to log function calls."""
    def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed with error: {e}")
            raise
    return wrapper


def log_performance(func):
    """Decorator to log function performance."""
    import time
    
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.log("PERFORMANCE", f"{func.__name__} executed in {execution_time:.4f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {execution_time:.4f}s: {e}")
            raise
    return wrapper


# Initialize logging when module is imported
setup_logging()
