import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from asyncpg import Connection
from typing import Dict, Any

from app.core.dependencies import get_db_connection, get_current_user_id
from app.schemas.alert_schemas import AlertParametersUpdate, AlertParametersResponse
from app.utils import parse_db_response # Função utilitária para JSON

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/alerts/parameters/{monitored_user_id}",
    response_model=AlertParametersResponse,
    summary="Obter parâmetros de alerta (tolerância) de um utilizador monitorado"
)
async def get_alert_parameters(
    monitored_user_id: UUID,
    db: Connection = Depends(get_db_connection),
    # O utilizador autenticado (monitor) DEVE ter acesso a este utilizador monitorado.
    # Esta verificação será adicionada na rota de perfil/monitorização.
    current_user_id: str = Depends(get_current_user_id) 
):
    """
    Obtém os parâmetros de alerta (tolerance_minutes e min_movement_meters) para 
    um utilizador monitorado específico.
    """
    try:
        # A função SQL é api.get_alert_parameters_api
        query = f"SELECT api.get_alert_parameters_api($1::UUID);"
        
        # O resultado é JSON, que o parse_db_response irá desserializar.
        result_json = await db.fetchval(query, monitored_user_id)
        
        response_data = parse_db_response(result_json)

        if response_data.get("status") == "not_found":
             # Se não for encontrado, a DB devolve os valores predefinidos (30, 10)
            return AlertParametersResponse(
                status="success", # Ainda é um sucesso, pois devolve defaults
                tolerance_minutes=response_data.get("tolerance_minutes"),
                min_movement_meters=response_data.get("min_movement_meters"),
                message="Parâmetros não definidos. A usar valores predefinidos."
            )

        return AlertParametersResponse(
            status=response_data.get("status", "error"),
            tolerance_minutes=response_data.get("tolerance_minutes"),
            min_movement_meters=response_data.get("min_movement_meters"),
        )
        
    except Exception as e:
        logger.error(f"Erro ao obter parâmetros de alerta para {monitored_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao aceder aos parâmetros de alerta."
        )


@router.put(
    "/alerts/parameters",
    summary="Definir/Atualizar parâmetros de alerta para um utilizador monitorado"
)
async def upsert_alert_parameters(
    params: AlertParametersUpdate,
    db: Connection = Depends(get_db_connection),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Define ou atualiza os parâmetros de alerta de um idoso.
    Estes parâmetros controlam o tempo que o idoso pode desviar-se da rotina (tolerance_minutes) 
    e o limiar de ruído do GPS (min_movement_meters).
    """
    try:
        # Cria o payload JSON para a função SQL
        payload = {
            "user_id": str(params.monitored_user_id),
            "tolerance_minutes": params.tolerance_minutes,
            "min_movement_meters": params.min_movement_meters
        }

        # A função SQL é api.upsert_alert_parameters_api
        query = f"SELECT api.upsert_alert_parameters_api($1::JSONB);"
        
        # O resultado é JSON, que o parse_db_response irá desserializar.
        result_json = await db.fetchval(query, payload)
        
        response_data = parse_db_response(result_json)

        if response_data.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=response_data.get("message", "Erro desconhecido ao definir parâmetros.")
            )

        return {"status": "success", "message": "Parâmetros de alerta atualizados com sucesso."}

    except HTTPException:
        # Re-raise HTTPExceptions (como o 400 da validação SQL)
        raise
    except Exception as e:
        logger.error(f"Erro ao definir parâmetros de alerta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar a atualização dos parâmetros."
        )
