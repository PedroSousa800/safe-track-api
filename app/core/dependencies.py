# app/core/dependencies.py

from fastapi import Request, HTTPException, status, Depends
import asyncpg
import logging
from typing import AsyncGenerator # Adiciona a importação necessária para o type hint
from jose import jwt, JWTError  # Import jwt and JWTError for exception handling
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings  # Import the settings object
from app.schemas.user import TokenData

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_db_connection(request: Request) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Dependência que injeta uma conexão do pool.
    """
    pool = request.app.state.db_pool
    
    if not pool:
        logger.error("Database connection pool is not initialized.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Serviço de banco de dados indisponível."
        )
        
    async with pool.acquire() as conn:
        yield conn

async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dependência para extrair o ID do usuário do token JWT.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_data = TokenData(email=user_id) # O 'sub' do token é o user_id, não o email, mas o schema TokenData aceita uma string
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
