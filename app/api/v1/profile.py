# app/api/v1/profile.py
from fastapi import APIRouter, HTTPException, Depends, status
import asyncpg
import json
import logging
from uuid import UUID

from app.schemas.user import UserProfileUpdate # Importação corrigida
from app.core.dependencies import get_db_connection, get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/users",
    tags=["Profile"],
)

@router.patch("/{user_id}/profile_type", status_code=status.HTTP_200_OK)
async def update_user_profile(
    user_id: UUID,
    profile_data: UserProfileUpdate,
    db: asyncpg.Connection = Depends(get_db_connection),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Atualiza o tipo de perfil de um usuário.
    """
    if user_id != UUID(current_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You can only update your own profile.")

    try:
        raw_result = await db.fetchval(
            "SELECT api.update_user_profile($1::uuid, $2::varchar)",
            user_id,
            profile_data.profile_type
        )
        
        if isinstance(raw_result, str):
            response_data = json.loads(raw_result)
        else:
            response_data = raw_result

        if response_data.get("status") == "success":
            return response_data
        elif response_data.get("status") == "user_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=response_data)
        elif response_data.get("status") == "profile_already_set":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=response_data)
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response_data)

    except HTTPException:
        raise
    except asyncpg.exceptions.PostgresError as e:
        logger.error(f"Database error during profile update: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "Database error during profile update.", "error": str(e)})
    except Exception as e:
        logger.error(f"An unexpected error occurred during profile update: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "An unexpected error occurred.", "error": str(e)})
