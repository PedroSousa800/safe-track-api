import asyncio
import logging
from fastapi import FastAPI, HTTPException, status, Request
from pydantic import BaseModel
from redis.asyncio import Redis 
from fastapi_limiter import FastAPILimiter

from contextlib import asynccontextmanager
from asyncpg import Connection

import asyncpg

from app.core.config import settings
from app.api.v1 import register, authentication, profile, location, alert_parameters, patterns # NOVOS IMPORTS DE AI
from app.db.wait_for_db import initialize_db_pool_with_retry 
from app.ai.scheduler import start_scheduler, stop_scheduler, initialize_job_store # NOVO IMPORT DO SCHEDULER

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
    E para inicializar e fechar a conexão com o Redis/Rate Limiter e o Scheduler.
    """
    
    # --- 1. Inicialização da Pool de Conexões (AGORA COM RETRY) ---
    try:
        db_pool = await initialize_db_pool_with_retry(max_retries=10, delay=2) 
        app.state.db_pool = db_pool
        
        # ⚠️ IMPORTANTE: Inicializa a JobStore do Scheduler com o pool de DB
        initialize_job_store(db_pool)
        
    except Exception as e:
        logger.error(f"FATAL: Application failed to start due to persistent DB connection failure.")
        raise
        
    # --- 2. Inicialização do Rate Limiter e Redis ---
    try:
        redis = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        await FastAPILimiter.init(redis)
        app.state.redis = redis
        logger.info("FastAPILimiter e Redis inicializados com sucesso.")
    except Exception as e:
        logger.error(f"Falha ao inicializar o Redis/FastAPILimiter. O Rate Limiting não estará ativo. Erro: {e}")
    
    # --- 3. INICIALIZAÇÃO DO SCHEDULER DE IA (Fase 2) ---
    try:
        start_scheduler()
        logger.info("APScheduler iniciado com sucesso. A detecção de anomalias está ativa.")
    except Exception as e:
        logger.error(f"Falha ao iniciar o APScheduler. A detecção de anomalias automática não funcionará. Erro: {e}")
    
    # O ciclo de vida da aplicação começa
    yield
    
    # --- Shutdown do Scheduler.
    try:
        stop_scheduler()
        logger.info("APScheduler desligado.")
    except Exception as e:
        logger.error(f"Erro ao desligar o APScheduler: {e}")
        
    # --- Shutdown da Pool de Conexões.
    if hasattr(app.state, 'db_pool'):
        logger.info("Closing database connection pool...")
        await app.state.db_pool.close()
        logger.info("Database connection pool closed.")
        
    # --- Shutdown do Rate Limiter e Redis
    if hasattr(app.state, 'redis'):
        logger.info("Closing FastAPILimiter and Redis connection...")
        await FastAPILimiter.close() 
        logger.info("FastAPILimiter desligado.")


# Cria a instância da aplicação FastAPI com o contexto de lifespan
app = FastAPI(
    title="SafeTrack API",
    description="API para gerir utilizadores e competências, incluindo o motor de detecção de anomalias por IA.",
    version="1.0.0",
    lifespan=lifespan
)

# Rota de Health Check (Infraestrutura)
@app.get("/health", tags=["System"], response_model=dict)
def health_check():
    return {"status": "OK", "message": "API running"}


@app.get("/ready", tags=["System"], response_model=ReadinessStatus, summary="Verifica a prontidão da aplicação, incluindo dependências (DB e Cache).")
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
    if hasattr(request.app.state, 'db_pool'):
        try:
            async with request.app.state.db_pool.acquire() as connection:
                await connection.fetchval("SELECT 1")
            
            db_status = "UP"
        except Exception as e:
            db_status = f"DOWN: {str(e)}"
            is_ready = False
            logger.error(f"PostgreSQL Check Failed: {e}")
    else:
        db_status = "DOWN (Pool not initialized)"
        is_ready = False
        logger.error("Database Pool not found in app state.")


    # 2. Verificar Conexão com o Redis
    if hasattr(request.app.state, 'redis'):
        try:
            await request.app.state.redis.ping()
            
            redis_status = "UP"

        except Exception as e:
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

# NOVOS ROUTERS DO MOTOR DE IA
app.include_router(alert_parameters.router, prefix="/api/v1/alerts", tags=["Alerts & Monitoring"])
app.include_router(patterns.router, prefix="/api/v1/patterns", tags=["AI Pattern Management"])

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à SafeTrack API!"}
