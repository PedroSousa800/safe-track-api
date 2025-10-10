# app/api/v1/location.py
from fastapi import APIRouter, HTTPException, Depends, status
import asyncpg
import json
import logging
from uuid import UUID

# NOVAS IMPORTAÇÕES NECESSÁRIAS PARA O RATE LIMITING
from fastapi_limiter.depends import RateLimiter 
from app.utils.rate_limit_keys import user_id_key_func
from app.core.config import settings 

from app.schemas.user import LocationUpdate, LocationIntervalUpdate 
from app.core.dependencies import get_db_connection, get_current_user_id

from datetime import timezone # <-- NECESSÁRIO para a conversão para UTC

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/location",
    tags=["Location"],
)

@router.post(
    "/", 
    status_code=status.HTTP_201_CREATED,
    # ⬅️ APLICAÇÃO DO RATE LIMITER POR USER ID
    dependencies=[
        Depends(
            RateLimiter(
                times=settings.LOCATION_RATE_LIMIT_TIMES,          # Ex: 1
                seconds=settings.LOCATION_RATE_LIMIT_SECONDS,      # Ex: 5
                identifier=user_id_key_func # Usa o ID do utilizador (do token) para rastrear
            )
        )
    ]
)
async def create_location(
    location_data: LocationUpdate,
    db: asyncpg.Connection = Depends(get_db_connection),
    current_user_id: str = Depends(get_current_user_id) 
):
    """
    Registra a localização atual do usuário autenticado.
    Registra tanto o timestamp local do aplicativo (para contexto de IA) 
    quanto o timestamp UTC (para cálculo de duração).
    """
    try:
        # 1. Objeto de tempo com o fuso horário local (ex: 10:30:00+01:00)
        # Assumimos que o Pydantic já transformou a string de entrada num objeto datetime 'aware'.
        timestamp_app_local = location_data.timestamp
        
        # 2. Converte para UTC (ex: 09:30:00+00:00). Este é o valor para o cálculo de duração.
        timestamp_utc = timestamp_app_local.astimezone(timezone.utc)

        logger.info(f"timestamp_app_local {timestamp_app_local}")
        logger.info(f"timestamp_app_local.astimezone(timezone.utc) {timestamp_app_local.astimezone(timezone.utc)}")
        logger.info(f"timestamp_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00') {timestamp_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00')}")

        # 3. Constrói o objeto JSONB com os DOIS timestamps.
        location_payload = json.dumps({
            "user_id": current_user_id, 
            "latitude": location_data.latitude,
            "longitude": location_data.longitude,
            
            # Hora do cliente com offset de fuso horário (Para análise contextual de IA)
            "timestamp_app_local": timestamp_app_local.isoformat(), 
            
            # Hora UTC (Para cálculos de duração e padronização)
            "timestamp_utc": timestamp_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00')

        })

        logger.info(f"Location payload to DB: {location_payload}")
        
        # 4. Chama a função do DB. A função SQL deve ser atualizada para receber estes dois campos.
        raw_result = await db.fetchval(
            "SELECT api.insert_location($1::jsonb)",
            location_payload
        )
        
        if raw_result:
            response_data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            
            if response_data.get("status") == "success":
                # Mensagem de resposta para o cliente
                return {"message": "Localização registrada com sucesso!", "status": "success"}
        
        # Se o resultado for nulo ou não tiver status: success
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=response_data or {"message": "Falha ao inserir localização devido a uma resposta inesperada do banco de dados."}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao registrar localização: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Ocorreu um erro inesperado no servidor.", "error": str(e)}
        )

# --- Rotas Existentes (Mantidas sem alteração) ---

@router.get("/users/{user_id}/location-interval", status_code=status.HTTP_200_OK)
async def get_location_interval(
    user_id: UUID,
    db: asyncpg.Connection = Depends(get_db_connection),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Busca o intervalo de tempo em segundos para a atualização de localização de um usuário.
    """
    # Proteção de Self-Ownership CORRETA
    if user_id != UUID(current_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You can only retrieve your own location interval.")
    
    try:
        raw_result = await db.fetchval(
            "SELECT api.get_location_interval($1::uuid)",
            user_id
        )
        
        if isinstance(raw_result, str):
            response_data = json.loads(raw_result)
        else:
            response_data = raw_result

        if response_data.get("status") == "success":
            return {"interval_in_seconds": response_data.get("interval_in_seconds"), "status": "success"}
        elif response_data.get("status") == "user_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=response_data)
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response_data)

    except HTTPException:
        raise
    except asyncpg.exceptions.PostgresError as e:
        logger.error(f"Database error during location interval retrieval: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "Database error during location interval retrieval.", "error": str(e)})
    except Exception as e:
        logger.error(f"An unexpected error occurred during location interval retrieval: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "An unexpected error occurred.", "error": str(e)})

@router.patch("/users/{user_id}/location-interval", status_code=status.HTTP_200_OK)
async def update_location_interval(
    user_id: UUID,
    interval_data: LocationIntervalUpdate,
    db: asyncpg.Connection = Depends(get_db_connection),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Atualiza o intervalo de tempo em segundos para a atualização de localização de um usuário.
    """
    # Proteção de Self-Ownership CORRETA
    if user_id != UUID(current_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You can only update your own location interval.")
    
    try:
        raw_result = await db.fetchval(
            "SELECT api.set_location_interval($1::uuid, $2::integer)",
            user_id,
            interval_data.interval_in_seconds
        )
        
        if isinstance(raw_result, str):
            response_data = json.loads(raw_result)
        else:
            response_data = raw_result

        if response_data.get("status") == "success":
            return {"message": "Intervalo de localização atualizado com sucesso!", "status": "success"}
        elif response_data.get("status") == "user_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=response_data)
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response_data)

    except HTTPException:
        raise
    except asyncpg.exceptions.PostgresError as e:
        logger.error(f"Database error during location interval update: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "Database error during location interval update.", "error": str(e)})
    except Exception as e:
        logger.error(f"An unexpected error occurred during location interval update: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "An unexpected error occurred.", "error": str(e)})
