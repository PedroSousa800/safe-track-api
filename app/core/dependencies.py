# app/core/dependencies.py

from fastapi import Request, HTTPException, status, Depends
import asyncpg
import logging
from typing import AsyncGenerator
from jose import jwt, JWTError 

from app.core.config import settings 

# Removidas as importações OAuth2PasswordBearer e TokenData, pois a função agora
# extrai o token diretamente do Request.

logger = logging.getLogger(__name__)

# A variável oauth2_scheme foi removida porque get_current_user_id já não depende dela.

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

async def get_current_user_id(request: Request) -> str:
    """
    Dependência robusta para extrair e validar o ID do usuário de um token JWT.
    
    Recebe o objeto Request (necessário para o RateLimiter e outras dependências)
    e extrai o token manualmente do cabeçalho 'Authorization'.
    """
    
    # 1. Obter o valor do cabeçalho Authorization
    authorization: str | None = request.headers.get("Authorization")
    
    # 2. Verificar se o cabeçalho Authorization existe
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não foram fornecidas credenciais de autenticação.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 3. Processar o cabeçalho (esperado: "Bearer <token>")
    try:
        scheme, token = authorization.split()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de token inválido. O esperado é 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esquema de autenticação não suportado. Use 'Bearer'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 4. Decodificar o token
    try:
        # jwt.decode espera o token como uma string, agora token contém apenas o valor do JWT
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        
        user_id: str | None = payload.get("sub")
        
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido: ID do usuário ausente.")
            
        return user_id
        
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas ou token expirado.")
