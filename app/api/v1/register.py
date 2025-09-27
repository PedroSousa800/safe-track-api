# app/api/v1/register.py

from fastapi import APIRouter, HTTPException, Depends, status
import asyncpg
import json
import logging
from typing import Optional

from app.schemas.user import UserCreate
from app.core.dependencies import get_db_connection
from app.utils.auth import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/register",
    tags=["Register"],
)

@router.post("", status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,  # Recebe o modelo Pydantic no corpo da requisição, que inclui 'name'.
    db: asyncpg.Connection = Depends(get_db_connection)
):
    """
    Endpoint para registro de novos usuários.
    """
    hashed_password = get_password_hash(user_data.password)
    
    try:
        # A nova estrutura de dados para o JSON de entrada
        user_json = {
            "email": user_data.email,
            "password_hash": hashed_password,
            "name": user_data.name # Incluído novamente o campo 'name'
        }
        
        raw_result = await db.fetchval(
            "SELECT api.register_user_api($1::jsonb)",
            json.dumps(user_json)
        )
        
        if raw_result:
            response_data = json.loads(raw_result)
            if response_data.get("status") == "new_user_registered":
                return {"message": "Usuário registrado com sucesso! Por favor, finalize o registro com o seu PIN.", "status": "new_user_registered", "user_id": response_data.get("user_id")}

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=response_data.get("message")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao registrar usuário: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An unexpected error occurred.", "error": str(e)}
        )
