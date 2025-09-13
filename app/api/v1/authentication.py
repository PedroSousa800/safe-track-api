# app/api/v1/authentication.py
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
import asyncpg
import json
import logging
from datetime import timedelta
from uuid import UUID

from app.schemas.user import (
    UserFinalizePin,
    UserEmail,
    VerifyRecoveryTokenRequest,
    Token,
)
from app.core.dependencies import get_db_connection
from app.utils.auth import verify_password, create_access_token # <--- AQUI ESTÁ A CORREÇÃO
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# Placeholder para a função de envio de e-mail.
async def send_pin_recovery_email(email: str, token: str):
    """
    Função assíncrona para simular o envio de e-mail de recuperação de PIN.
    """
    logger.info(f"--- SIMULANDO ENVIO DE E-MAIL ---")
    logger.info(f"Para: {email}")
    logger.info(f"Assunto: Código de Recuperação de PIN SafeTrack")
    logger.info(f"Mensagem: Seu código de recuperação de PIN é: {token}")
    logger.info(f"--- FIM DA SIMULAÇÃO ---")

@router.post("/finalize-pin")
async def finalize_pin(pin_data: UserFinalizePin, db: asyncpg.Connection = Depends(get_db_connection)):
    """
    Finaliza o registro do usuário com o PIN fornecido.
    """
    try:
        raw_result = await db.fetchval (
            "SELECT api.finalize_registration_with_pin_api($1::jsonb)",
            pin_data.model_dump_json()
        )
        if isinstance(raw_result, str):
            result_dict = json.loads(raw_result)
        else:
            result_dict = raw_result

        if result_dict.get('status') == 'success':
            return {
                "message": result_dict['message'],
                "user_id": pin_data.user_id,
                "status": result_dict['status']
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": result_dict.get('message', 'Falha ao finalizar PIN.'),
                    "user_id": pin_data.user_id,
                    "status": result_dict.get('status', 'error')
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro na finalização do PIN: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/login")
async def login_user(form_data: OAuth2PasswordRequestForm = Depends(), db: asyncpg.Connection = Depends(get_db_connection)):
    """
    Endpoint para login de usuário.
    """
    try:
        login_credentials_json = json.dumps({"email": form_data.username, "pin": form_data.password})

        raw_result = await db.fetchval (
            "SELECT api.login_user_api($1::jsonb)",
            login_credentials_json
        )
        
        if isinstance(raw_result, str):
            result_dict = json.loads(raw_result)
        else:
            result_dict = raw_result

        if result_dict.get('status') == 'success':
            user_id_from_db = result_dict['user_id']
            
            access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": user_id_from_db}, expires_delta=access_token_expires
            )
            
            return {
                "message": result_dict['message'],
                "user_id": user_id_from_db,
                "profile_type": result_dict.get('profile_type_code'),
                "status": result_dict['status'],
                "access_token": access_token,
                "token_type": "bearer"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": result_dict.get('message', 'Falha no login.'),
                    "user_id": result_dict.get('user_id'),
                    "status": result_dict.get('status', 'error')
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado no login: {e}") 
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.post("/recover-pin", status_code=status.HTTP_200_OK)
async def recover_pin(user_email: UserEmail, background_tasks: BackgroundTasks, db: asyncpg.Connection = Depends(get_db_connection)):
    """
    Inicia o processo de recuperação de PIN.
    """
    try:
        raw_result = await db.fetchval(
            "SELECT api.start_pin_recovery_process_api_func($1)",
            user_email.email
        )
        
        if raw_result is not None:
            response_data = json.loads(raw_result)
            if response_data.get("status") == "recovery_started":
                token = response_data.get("token")
                if token:
                    background_tasks.add_task(send_pin_recovery_email, user_email.email, token)
            else:
                logger.error(f"Erro inesperado do DB no fluxo de recuperação de PIN: {response_data}")

    except Exception as e:
        logger.error(f"Unexpected error in PIN recovery flow: {e}")
    return {"message": "If an account with that email exists, a recovery code has been sent."}

@router.post("/verify-recovery-token")
async def verify_recovery_token(request: VerifyRecoveryTokenRequest, db: asyncpg.Connection = Depends(get_db_connection)):
    """
    Verifica se o token de recuperação é válido.
    """
    try:
        raw_result = await db.fetchval(
            "SELECT api.verify_recovery_token_api_func($1, $2)",
            request.email,
            request.token
        )
        
        if raw_result is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Token inválido ou expirado."}
            )

        response_data = json.loads(raw_result)

        if response_data.get("status") == "success":
            return {"message": "Token verificado com sucesso.", "user_id": response_data.get("user_id")}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": response_data.get("message", "Token inválido ou expirado.")}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro na verificação de token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An unexpected error occurred."}
        )
