"""
Authentication routes for user management and JWT tokens.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from app.db import get_db
from app.models import User
from app.config import settings
from loguru import logger

router = APIRouter()
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class TokenData(BaseModel):
    user_id: Optional[uuid.UUID] = None


class FyersAuthRequest(BaseModel):
    auth_code: str


class FyersAuthResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None


# Utility functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user_query = select(User).where(User.id == uuid.UUID(user_id))
    result = await db.execute(user_query)
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# Routes
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    # Check if user already exists
    existing_user_query = select(User).where(
        (User.email == user_data.email) | (User.username == user_data.username)
    )
    existing_user_result = await db.execute(existing_user_query)
    existing_user = existing_user_result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        is_active=True,
        is_verified=True,  # Auto-verify for now
        created_at=datetime.utcnow()
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    logger.info(f"New user registered: {user.email}")
    
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at
    )


@router.post("/login", response_model=Token)
async def login_user(user_credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login user and return access token."""
    # Find user by email
    user_query = select(User).where(User.email == user_credentials.email)
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()
    
    if not user or not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # Create tokens
    access_token_expires = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    logger.info(f"User logged in: {user.email}")
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at
    )


@router.post("/fyers/auth", response_model=FyersAuthResponse)
async def authenticate_fyers(
    auth_request: FyersAuthRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Authenticate with Fyers API and store credentials."""
    try:
        from app.services.fyers_client import FyersClient
        
        fyers_client = FyersClient()
        token_response = await fyers_client.get_access_token(auth_request.auth_code)
        
        if "access_token" in token_response:
            # Store Fyers credentials
            current_user.fyers_access_token = token_response["access_token"]
            current_user.fyers_refresh_token = token_response.get("refresh_token")
            
            # Calculate expiration time
            expires_in = token_response.get("expires_in", 3600)
            current_user.fyers_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            await db.commit()
            
            logger.info(f"Fyers authentication successful for user: {current_user.email}")
            
            return FyersAuthResponse(
                success=True,
                message="Fyers authentication successful",
                access_token=token_response["access_token"],
                refresh_token=token_response.get("refresh_token"),
                expires_at=current_user.fyers_token_expires_at
            )
        else:
            logger.error(f"Fyers authentication failed: {token_response}")
            return FyersAuthResponse(
                success=False,
                message="Fyers authentication failed"
            )
            
    except Exception as e:
        logger.error(f"Fyers authentication error: {e}")
        return FyersAuthResponse(
            success=False,
            message=f"Authentication error: {str(e)}"
        )


@router.get("/fyers/auth-url")
async def get_fyers_auth_url():
    """Get Fyers authentication URL."""
    try:
        from app.services.fyers_client import FyersClient
        
        fyers_client = FyersClient()
        auth_url = await fyers_client.get_auth_url()
        
        return {"auth_url": auth_url}
        
    except Exception as e:
        logger.error(f"Error generating Fyers auth URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authentication URL"
        )


@router.post("/refresh-token", response_model=Token)
async def refresh_access_token(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Refresh Fyers access token."""
    try:
        if not current_user.fyers_refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No refresh token available"
            )
        
        from app.services.fyers_client import FyersClient
        
        fyers_client = FyersClient()
        token_response = await fyers_client.refresh_access_token(current_user.fyers_refresh_token)
        
        if "access_token" in token_response:
            # Update stored credentials
            current_user.fyers_access_token = token_response["access_token"]
            current_user.fyers_refresh_token = token_response.get("refresh_token")
            
            expires_in = token_response.get("expires_in", 3600)
            current_user.fyers_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            await db.commit()
            
            logger.info(f"Fyers token refreshed for user: {current_user.email}")
            
            # Return new JWT token
            access_token_expires = timedelta(minutes=settings.jwt_access_token_expire_minutes)
            access_token = create_access_token(
                data={"sub": str(current_user.id)}, expires_delta=access_token_expires
            )
            
            return Token(
                access_token=access_token,
                token_type="bearer",
                expires_in=settings.jwt_access_token_expire_minutes * 60
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to refresh token"
            )
            
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )
