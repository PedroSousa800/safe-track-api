import asyncio
import logging
from fastapi import FastAPI, HTTPException, status, Request
# Removida a importação de fastapi.security.HTTPBearer
from pydantic import BaseModel
from redis.asyncio import Redis 
from fastapi_limiter import FastAPILimiter

from contextlib import asynccontextmanager
from asyncpg import Connection # Connection não é necessário na rota /ready, mas é mantido se for usado noutro local

import asyncpg

from app.core.config import settings
from app.api.v1 import register, authentication, profile, location
from app.db.wait_for_db import initialize_db_pool_with_retry # IMPORTANTE: Nova função de retry

# --- Modelos de Resposta ---
class Status(BaseModel):
    """Modelo de resposta para verificações de saúde e prontidão."""
    status: str
    message: str

class ReadinessStatus(BaseModel):
    """Modelo detalhado para o Readiness Check."""
    status: str
    db_status: str
    redis_status: str
    message: str


# Configurar o logging
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Definir um contexto de lifespan para gerir o ciclo de vida da aplicação
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Função de lifespan para inicializar e fechar o pool de conexões com a base de dados
    E para inicializar e fechar a conexão com o Redis/Rate Limiter.
    """
    
    # --- 1. Inicialização da Pool de Conexões (AGORA COM RETRY) ---
    try:
        # Usa a nova função que tenta conectar-se várias vezes
        # Configurado para 10 tentativas com 2 segundos de atraso (total de 20s de espera)
        db_pool = await initialize_db_pool_with_retry(max_retries=10, delay=2) 
        app.state.db_pool = db_pool
    except Exception as e:
        # Se falhar após todas as retries (10 * 2 segundos), a app falha
        logger.error(f"FATAL: Application failed to start due to persistent DB connection failure.")
        raise
        
    # Inicialização do Rate Limiter e Redis.
    try:
        # A URL do Redis vem do settings (lido do .env ou Railway)
        redis = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        await FastAPILimiter.init(redis)
        app.state.redis = redis # Armazena a instância Redis no estado da App
        logger.info("FastAPILimiter e Redis inicializados com sucesso.")
    except Exception as e:
        # Se o Redis falhar, registamos o erro, mas permitimos que o servidor inicie.
        logger.error(f"Falha ao inicializar o Redis/FastAPILimiter. O Rate Limiting não estará ativo. Erro: {e}")
        # Não levanta 'raise' aqui, para permitir que o resto da app funcione.

    # O ciclo de vida da aplicação começa
    yield
    
    # --- Shutdown da Pool de Conexões.
    if hasattr(app.state, 'db_pool'):
        logger.info("Closing database connection pool...")
        await app.state.db_pool.close()
        logger.info("Database connection pool closed.")
        
    # --- Shutdown do Rate Limiter e Redis
    # Verifica se o Redis foi inicializado com sucesso antes de tentar fechar
    if hasattr(app.state, 'redis'):
        logger.info("Closing FastAPILimiter and Redis connection...")
        # FastAPILimiter.close() fecha a conexão Redis subjacente
        await FastAPILimiter.close() 
        logger.info("FastAPILimiter desligado.")


# Cria a instância da aplicação FastAPI com o contexto de lifespan
app = FastAPI(
    title="SafeTrack API",
    description="API para gerir utilizadores e competências",
    version="1.0.0",
    lifespan=lifespan
    # REMOVIDO: o bloco openapi_extra para limpar o código.
)

# Rota de Health Check (Infraestrutura)
@app.get("/health", tags=["System"], response_model=dict)
def health_check():
    return {"status": "OK", "message": "API running"}


@app.get("/ready", tags=["System"], response_model=ReadinessStatus, summary="Verifica a prontidão da aplicação, incluindo dependências (DB e Cache).")
# Recebe o objeto Request para aceder ao estado da aplicação (app.state.db_pool e app.state.redis)
async def readiness_check(request: Request): 
    """
    Verificação de Readiness (Prontidão).
    Verifica a conexão com a Base de Dados (PostgreSQL) e o Cache (Redis).
    Se qualquer dependência falhar, retorna status 503.
    """
    db_status = "DOWN"
    redis_status = "DOWN"
    is_ready = True

    # 1. Verificar Conexão com o PostgreSQL
    # CRITICAL FIX: Deve adquirir uma conexão do pool da app.state para executar o ping.
    if hasattr(request.app.state, 'db_pool'):
        try:
            # Adquire uma conexão do pool de forma assíncrona para o teste
            async with request.app.state.db_pool.acquire() as connection:
                # Executa uma query de teste simples e rápida
                await connection.fetchval("SELECT 1")
            
            db_status = "UP"
        except Exception as e:
            # Em caso de falha na conexão ou na query
            db_status = f"DOWN: {str(e)}"
            is_ready = False
            logger.error(f"PostgreSQL Check Failed: {e}")
    else:
        db_status = "DOWN (Pool not initialized)"
        is_ready = False
        logger.error("Database Pool not found in app state.")


    # 2. Verificar Conexão com o Redis
    # CRITICAL FIX: Deve usar a instância Redis armazenada no estado da app.
    if hasattr(request.app.state, 'redis'):
        try:
            # Usa o objeto Redis da app.state para enviar o comando PING
            await request.app.state.redis.ping()
            
            redis_status = "UP"

        except Exception as e:
            # Em caso de falha na conexão ou no comando PING
            redis_status = f"DOWN: {str(e)}"
            is_ready = False
            logger.error(f"Redis Check Failed: {e}")
    else:
        redis_status = "DOWN (Redis client not initialized)"
        is_ready = False
        logger.error("Redis client not found in app state.")

    # 3. Retornar o Status de Prontidão
    if is_ready:
        return ReadinessStatus(
            status="READY",
            db_status=db_status,
            redis_status=redis_status,
            message="Application is ready and all dependencies are UP."
        )
    else:
        # Se alguma dependência falhar, retorna um erro 503 (Service Unavailable)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ReadinessStatus(
                status="NOT READY",
                db_status=db_status,
                redis_status=redis_status,
                message="One or more critical dependencies are DOWN."
            ).dict()
        )

# Inclui os routers existentes
app.include_router(register.router, prefix="/api/v1", tags=["Register"])
app.include_router(authentication.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(profile.router, prefix="/api/v1", tags=["Profile"])
app.include_router(location.router, prefix="/api/v1", tags=["Location"])

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à SafeTrack API!"}
