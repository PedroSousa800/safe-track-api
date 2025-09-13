# app/api/v1/location.py
from fastapi import APIRouter, HTTPException, Depends, status
import asyncpg
import json
import logging
from uuid import UUID

from app.schemas.user import LocationUpdate, LocationIntervalUpdate # Importações corrigidas
from app.core.dependencies import get_db_connection, get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/location",
    tags=["Location"],
)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_location(
    location_data: LocationUpdate,
    db: asyncpg.Connection = Depends(get_db_connection),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Registra a localização atual do usuário.
    """
    try:
        raw_result = await db.fetchval(
            "SELECT api.insert_location($1::jsonb)",
            json.dumps({
                "user_id": current_user_id,
                "latitude": location_data.latitude,
                "longitude": location_data.longitude,
                "accuracy": location_data.accuracy,
                "timestamp": location_data.timestamp.isoformat()
            })
        )
        
        if raw_result:
            response_data = json.loads(raw_result)
            if response_data.get("status") == "success":
                return {"message": "Localização registrada com sucesso!", "status": "success"}
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to insert location due to an unexpected database response."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao registrar localização: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An unexpected error occurred.", "error": str(e)}
        )

@router.get("/users/{user_id}/location-interval", status_code=status.HTTP_200_OK)
async def get_location_interval(
    user_id: UUID,
    db: asyncpg.Connection = Depends(get_db_connection),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Busca o intervalo de tempo em segundos para a atualização de localização de um usuário.
    """
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
