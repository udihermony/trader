"""
Configuration management for the Algorithmic Trading Platform.
Handles environment variables, AWS SSM integration, and settings validation.
"""

import os
from typing import List, Optional
from functools import lru_cache

from pydantic import BaseSettings, Field, validator
from pydantic_settings import BaseSettings as PydanticBaseSettings


class Settings(PydanticBaseSettings):
    """Application settings with environment variable support."""
    
    # Application Settings
    app_name: str = Field(default="AlgoTrader", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="production", env="ENVIRONMENT")
    
    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    workers: int = Field(default=1, env="WORKERS")
    
    # Database Configuration
    database_url: str = Field(env="DATABASE_URL")
    database_pool_size: int = Field(default=10, env="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")
    
    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    # Fyers API Configuration
    fyers_app_id: str = Field(env="FYERS_APP_ID")
    fyers_secret_key: str = Field(env="FYERS_SECRET_KEY")
    fyers_redirect_uri: str = Field(env="FYERS_REDIRECT_URI")
    fyers_base_url: str = Field(default="https://api-t1.fyers.in/api/v3", env="FYERS_BASE_URL")
    
    # JWT Configuration
    jwt_secret_key: str = Field(env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_refresh_token_expire_days: int = Field(default=7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")
    
    # AWS Configuration
    aws_region: str = Field(default="ap-south-1", env="AWS_REGION")
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_ssm_prefix: str = Field(default="/alogtrader/", env="AWS_SSM_PREFIX")
    
    # Chartlink Webhook Configuration
    chartlink_webhook_secret: str = Field(env="CHARTLINK_WEBHOOK_SECRET")
    chartlink_webhook_endpoint: str = Field(default="/webhooks/chartlink", env="CHARTLINK_WEBHOOK_ENDPOINT")
    
    # Risk Management
    max_position_size: float = Field(default=100000.0, env="MAX_POSITION_SIZE")
    max_daily_loss: float = Field(default=5000.0, env="MAX_DAILY_LOSS")
    max_daily_trades: int = Field(default=50, env="MAX_DAILY_TRADES")
    
    # Monitoring
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")
    telegram_bot_token: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, env="TELEGRAM_CHAT_ID")
    
    # CORS Configuration
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="ALLOWED_ORIGINS"
    )
    allowed_methods: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        env="ALLOWED_METHODS"
    )
    allowed_headers: List[str] = Field(
        default=["*"],
        env="ALLOWED_HEADERS"
    )
    
    @validator("allowed_origins", "allowed_methods", "allowed_headers", pre=True)
    def parse_list_from_string(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",")]
        return v
    
    @validator("environment")
    def validate_environment(cls, v):
        """Validate environment setting."""
        allowed_envs = ["development", "staging", "production"]
        if v not in allowed_envs:
            raise ValueError(f"Environment must be one of {allowed_envs}")
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level setting."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of {allowed_levels}")
        return v.upper()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


class AWSConfig:
    """AWS-specific configuration and SSM integration."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._ssm_client = None
    
    @property
    def ssm_client(self):
        """Lazy-loaded SSM client."""
        if self._ssm_client is None:
            import boto3
            self._ssm_client = boto3.client(
                'ssm',
                region_name=self.settings.aws_region,
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key
            )
        return self._ssm_client
    
    async def get_parameter(self, parameter_name: str, decrypt: bool = True) -> str:
        """Get parameter from AWS SSM Parameter Store."""
        try:
            response = self.ssm_client.get_parameter(
                Name=f"{self.settings.aws_ssm_prefix}{parameter_name}",
                WithDecryption=decrypt
            )
            return response['Parameter']['Value']
        except Exception as e:
            raise ValueError(f"Failed to get parameter {parameter_name}: {e}")
    
    async def get_parameters(self, parameter_names: List[str], decrypt: bool = True) -> dict:
        """Get multiple parameters from AWS SSM Parameter Store."""
        try:
            names = [f"{self.settings.aws_ssm_prefix}{name}" for name in parameter_names]
            response = self.ssm_client.get_parameters(
                Names=names,
                WithDecryption=decrypt
            )
            return {
                param['Name'].replace(self.settings.aws_ssm_prefix, ''): param['Value']
                for param in response['Parameters']
            }
        except Exception as e:
            raise ValueError(f"Failed to get parameters {parameter_names}: {e}")


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


@lru_cache()
def get_aws_config() -> AWSConfig:
    """Get cached AWS configuration."""
    return AWSConfig(get_settings())


# Export commonly used settings
settings = get_settings()
aws_config = get_aws_config()
