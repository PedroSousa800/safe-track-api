# app/ai/detection.py

import logging
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from asyncpg.pool import Pool as AsyncpgPool

# Importar o serviço de e-mail para a Fase 3 (Alerta)
from app.services.email import send_anomaly_alert_email

if TYPE_CHECKING:
    from asyncpg.pool import Pool

logger = logging.getLogger(__name__)

# --- Funções de Ajuda para a Fase 3: Alerta ---

async def get_user_and_monitor_info(conn, monitored_id: str) -> dict | None:
    """
    Busca os emails do utilizador monitorizado e do monitor (guardados no perfil).
    """
    query = """
    SELECT 
        u.email AS monitored_email,
        m.email AS monitor_email,
        u.name AS monitored_name
    FROM 
        core.user u
    JOIN 
        core.user m ON u.monitor_user_id = m.user_id
    WHERE 
        u.user_id = $1;
    """
    record = await conn.fetchrow(query, monitored_id)
    return dict(record) if record else None

async def handle_anomaly_alert(
    db_pool: AsyncpgPool,
    monitored_id: str, 
    deviation_minutes: int, 
    expected_location: str
):
    """
    Fase 3: Aciona a notificação de alerta por e-mail e regista a anomalia na DB.
    """
    logger.warning(f"ALERTA: Desvio de {deviation_minutes}m detetado para {monitored_id}!")

    async with db_pool.acquire() as conn:
        # 1. Obter informações de contacto (monitor e monitorizado)
        contact_info = await get_user_and_monitor_info(conn, monitored_id)
        
        if not contact_info:
            logger.error(f"Não foi possível encontrar o monitor ou o utilizador {monitored_id}.")
            return

        # 2. Enviar o Alerta por E-mail
        try:
            await send_anomaly_alert_email(
                monitor_email=contact_info['monitor_email'],
                monitored_name=contact_info['monitored_name'],
                deviation_minutes=deviation_minutes,
                expected_location=expected_location
            )
            logger.info(f"Email de alerta enviado para {contact_info['monitor_email']}.")
        except Exception as e:
            logger.error(f"Falha ao enviar e-mail de alerta para {contact_info['monitor_email']}: {e}")

        # 3. Registrar a Anomalia na Base de Dados (chamada à função core/api)
        try:
            # Assumimos que o API/CORE terá uma função para registrar anomalias.
            await conn.execute(
                "SELECT api.register_anomaly($1, $2, $3)", 
                monitored_id, 
                deviation_minutes, 
                expected_location
            )
            logger.info(f"Anomalia registrada na DB para {monitored_id}.")
        except Exception as e:
            logger.error(f"Falha ao registrar anomalia na DB: {e}")

# --- Função Principal do Scheduler (Fase 2: Detecção) ---

async def check_all_monitored_users_for_anomaly(db_pool: AsyncpgPool):
    """
    Executado a cada 5 minutos pelo APScheduler.
    Verifica a localização atual de todos os utilizadores monitorizados contra os seus padrões.
    """
    logger.info("--- Iniciando verificação de anomalias (Execução do Scheduler) ---")
    current_time_utc = datetime.now(timezone.utc)

    async with db_pool.acquire() as conn:
        # 1. Obter Utilizadores Ativos e Parâmetros de Alerta
        # Retorna: user_id, pattern (JSONB), tolerance_minutes
        try:
            monitored_users_data = await conn.fetch("""
                SELECT 
                    ap.user_id, 
                    up.pattern, 
                    ap.tolerance_minutes 
                FROM 
                    api.alert_parameters ap
                JOIN 
                    api.user_patterns up ON ap.user_id = up.user_id
                WHERE
                    ap.is_active = TRUE; -- Apenas utilizadores com monitorização ativa
            """)
        except Exception as e:
            logger.error(f"Falha ao buscar utilizadores monitorizados/padrões: {e}")
            return
    
    if not monitored_users_data:
        logger.info("Nenhum utilizador com monitorização ativa e padrões definidos.")
        return

    for user_data in monitored_users_data:
        user_id = user_data['user_id']
        pattern_data = user_data['pattern']
        tolerance_minutes = user_data['tolerance_minutes']

        # 2. Obter a última localização conhecida do utilizador
        last_location = None
        try:
            async with db_pool.acquire() as conn:
                last_location = await conn.fetchrow("""
                    SELECT 
                        latitude, 
                        longitude, 
                        created_at 
                    FROM 
                        core.location 
                    WHERE 
                        user_id = $1 
                    ORDER BY 
                        created_at DESC 
                    LIMIT 1
                """, user_id)
        except Exception as e:
            logger.error(f"Falha ao buscar última localização para {user_id}: {e}")
            continue

        if not last_location:
            logger.info(f"Nenhuma localização encontrada para o utilizador {user_id}.")
            continue

        # 3. Processar o Padrão do Utilizador (JSONB)
        patterns = pattern_data['patterns']
        
        # 4. Encontrar a localização esperada mais próxima no padrão
        expected_location = None
        expected_time_utc = None
        min_time_diff_minutes = float('inf')
        
        current_minute_of_day = current_time_utc.hour * 60 + current_time_utc.minute

        for pattern in patterns:
            start_minute_of_day = pattern['start_hour'] * 60 + pattern['start_minute']
            end_minute_of_day = pattern['end_hour'] * 60 + pattern['end_minute']
            
            # Simplificação: Apenas verificamos se o tempo atual está dentro de qualquer intervalo
            # e calculamos o tempo esperado (usamos o ponto central do intervalo)
            if start_minute_of_day <= current_minute_of_day <= end_minute_of_day:
                
                # Para maior robustez, calculamos a diferença de tempo até ao final do intervalo
                time_diff_minutes = end_minute_of_day - current_minute_of_day

                if time_diff_minutes < min_time_diff_minutes:
                    min_time_diff_minutes = time_diff_minutes
                    expected_location = pattern['name']
                    # Usamos o final do intervalo como o ponto de referência para 'expected_time'
                    expected_time_utc = current_time_utc.replace(
                        hour=pattern['end_hour'], 
                        minute=pattern['end_minute'], 
                        second=0, 
                        microsecond=0
                    )
        
        # 5. Avaliação da Anomalia
        
        if expected_location and expected_time_utc:
            # 5a. O utilizador deveria estar num local de rotina neste momento.
            
            # Calcula a diferença de tempo entre o último reporte de localização e o tempo esperado de rotina
            location_time_diff = (current_time_utc - last_location['created_at']).total_seconds() / 60
            
            # Se o último reporte for muito antigo, consideramos um desvio de tempo:
            if location_time_diff > tolerance_minutes:
                logger.info(f"{user_id}: Localização atual ('{last_location['latitude']:.4f},{last_location['longitude']:.4f}') não corresponde ao esperado '{expected_location}'.")
                
                # ALERTA: Desvio detetado (Fase 3)
                # O desvio é o tempo em minutos desde o último reporte
                await handle_anomaly_alert(
                    db_pool,
                    user_id,
                    int(location_time_diff),
                    expected_location
                )
            else:
                # 5b. Se o último reporte for recente (dentro da tolerância), a rotina está OK.
                logger.info(f"{user_id}: Dentro da rotina. Último reporte: {location_time_diff:.1f}m atrás.")

        else:
            # 5c. O utilizador não tem um padrão de rotina esperado para este momento.
            logger.info(f"{user_id}: Tempo atual não coberto por padrões de rotina.")

    logger.info("--- Verificação de anomalias concluída ---")
