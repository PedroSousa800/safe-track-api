# app/ai/scheduler.py

import logging
from asyncpg import pool as asyncpg_pool
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from typing import TYPE_CHECKING
from app.core.config import settings

# Importar a função de detecção (precisamos do DB para a passar)
from app.ai.detection import check_all_monitored_users_for_anomaly

if TYPE_CHECKING:
    # Apenas para anotação de tipo, não é necessário importar o DB_POOL na runtime
    from asyncpg.pool import Pool

logger = logging.getLogger(__name__)

# O APScheduler usa o SQLAlchemy para comunicação com o PostgreSQL,
# não o asyncpg diretamente, por isso configuramos a connection string.
# NOTE: Certifique-se de que a biblioteca 'psycopg2-binary' está instalada
# (ou incluída no requirements.txt, o que já fizemos).
SCHEDULER_JOBSTORES = {
    'default': SQLAlchemyJobStore(
        url=settings.DB_DSN_SQLALCHEMY,  # DSN format necessário para SQLAlchemy
        tablename='apscheduler_jobs'
    )
}

SCHEDULER_EXECUTORS = {
    'default': AsyncIOExecutor()
}

# Inicialização do Scheduler
scheduler = AsyncIOScheduler(
    jobstores=SCHEDULER_JOBSTORES,
    executors=SCHEDULER_EXECUTORS,
    timezone="UTC"  # O scheduler deve sempre trabalhar em UTC
)

async def start_scheduler(db_pool: 'Pool'):
    """
    Inicializa e liga o APScheduler, e adiciona o job de detecção de anomalias.
    Esta função é chamada durante o lifespan do FastAPI.
    """
    logger.info("Scheduler: Inicializando o serviço APScheduler...")

    # A função principal do scheduler precisa do pool da DB para se conectar
    # e executar as verificações. Passamos o pool da DB para a função de job.
    
    # 1. Adiciona o job de detecção de anomalias, se ainda não existir.
    # O 'id' garante que apenas um job é adicionado.
    job_id = 'anomaly_detection_job'

    if scheduler.get_job(job_id) is None:
        # Frequência: Corre a cada 5 minutos (interval=5m)
        scheduler.add_job(
            func=check_all_monitored_users_for_anomaly, 
            trigger='interval', 
            minutes=5, 
            id=job_id,
            name="Anomaly Pattern Check",
            # Argumentos que serão passados para a função check_all_monitored_users_for_anomaly
            kwargs={'db_pool': db_pool}
        )
        logger.info(f"Scheduler: Job '{job_id}' (execução a cada 5m) adicionado com sucesso.")
    else:
        logger.info(f"Scheduler: Job '{job_id}' já existia.")
    
    # 2. Inicia o scheduler
    scheduler.start()
    logger.info("Scheduler: APScheduler iniciado e rodando.")

async def stop_scheduler():
    """
    Desliga o APScheduler, chamada durante o lifespan do FastAPI.
    """
    if scheduler.running:
        logger.info("Scheduler: Desligando o APScheduler...")
        scheduler.shutdown()
        logger.info("Scheduler: APScheduler desligado.")
