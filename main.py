# main.py

import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from asyncpg import Connection
import asyncpg

from app.core.config import settings
from app.api.v1 import register, authentication, profile, location

# Configurar o logging
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Definir um contexto de lifespan para gerir o ciclo de vida da aplicação
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Função de lifespan para inicializar e fechar o pool de conexões com a base de dados.
    """
    logger.info("Initializing database connection pool...")
    try:
        # Cria o pool de conexões usando as configurações do seu ficheiro .env
        db_pool = await asyncpg.create_pool(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            timeout=settings.DB_POOL_TIMEOUT_SECONDS
        )
        app.state.db_pool = db_pool
        logger.info("Database connection pool initialized.")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize database connection pool: {e}")
        raise
    finally:
        # Fecha o pool de conexões
        if 'db_pool' in app.state:
            logger.info("Closing database connection pool...")
            await app.state.db_pool.close()
            logger.info("Database connection pool closed.")


# Cria a instância da aplicação FastAPI com o contexto de lifespan
app = FastAPI(
    title="SafeTrack API",
    description="API para gerir utilizadores e competências",
    version="1.0.0",
    lifespan=lifespan
)

# Inclui os routers existentes
app.include_router(register.router, prefix="/api/v1", tags=["Register"])
app.include_router(authentication.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(profile.router, prefix="/api/v1", tags=["Profile"])
app.include_router(location.router, prefix="/api/v1", tags=["Location"])

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à SafeTrack API!"}
