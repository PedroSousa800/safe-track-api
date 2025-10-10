import asyncio
import logging
from asyncpg import create_pool
from app.core.config import settings

# Configurar logging para este módulo
logger = logging.getLogger(__name__)

async def initialize_db_pool_with_retry(max_retries: int = 5, delay: int = 3):
    """
    Tenta criar o pool de conexões com o PostgreSQL, com lógica de retry.
    Isto é crucial para resolver a race condition em ambientes Docker Compose.
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Attempt {attempt}/{max_retries}: Initializing database connection pool...")
            
            # Tenta criar o pool
            db_pool = await create_pool(
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                database=settings.DB_NAME,
                host=settings.DB_HOST, # Usará 'postgres'
                port=settings.DB_PORT, # Usará 5432
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
                timeout=settings.DB_POOL_TIMEOUT_SECONDS
            )
            logger.info("Database connection pool initialized successfully.")
            return db_pool

        except Exception as e:
            logger.warning(f"Connection failed on attempt {attempt}: {e}")
            if attempt < max_retries:
                logger.warning(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                # Na última tentativa, levanta a exceção, o que fará o FastAPI falhar.
                logger.error("Failed to initialize database connection pool after all retries.")
                raise e
    
    # Por segurança, caso o loop termine de forma inesperada (nunca deveria ocorrer)
    raise Exception("Could not initialize DB pool after max retries.")
