# app/api/v1/authentication.py
import os
import bcrypt
import random
import json
import logging
from uuid import UUID
from datetime import timedelta, datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
import asyncpg

from app.schemas.user import (
    UserFinalizePin,
    UserEmail,
    VerifyRecoveryTokenRequest,
    Token,
)
from app.core.dependencies import get_db_connection
from app.utils.auth import verify_password, create_access_token
from app.core.config import settings
# Importamos a função de serviço de email real
from app.services.email_service import send_pin_recovery_email

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# --- INÍCIO DAS NOVAS FUNÇÕES ---
def generate_pin_code():
    """Gera um PIN de 6 dígitos."""
    return str(random.randint(100000, 999999))

def hash_pin_code(pin: str) -> str:
    """Cria um hash bcrypt de um PIN."""
    # O sal é gerado automaticamente pelo bcrypt
    hashed = bcrypt.hashpw(pin.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')
# --- FIM DAS NOVAS FUNÇÕES ---

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
async def recover_pin(
    user_email: UserEmail, 
    background_tasks: BackgroundTasks, 
    db: asyncpg.Connection = Depends(get_db_connection)
):
    """
    Inicia o processo de recuperação de PIN.
    """
    try:
        # 1. Chamar a função do DB para iniciar o processo de recuperação (verifica se o utilizador existe)
        raw_result = await db.fetchval(
            "SELECT api.start_pin_recovery_process_api($1)",
            user_email.email
        )
        
        # Se a função do DB não retornar nada (resultado nulo ou erro de DB)
        if raw_result is None:
            # ERRO INTERNO GRAVE (DB está offline, erro de conexão, etc.)
            logger.error(f"Erro de conexão/execução com o DB ao iniciar recuperação para: {user_email.email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno do servidor. Não foi possível iniciar o processo de recuperação."
            )
            
        response_data = json.loads(raw_result)
        
        # Tratamento de erros de LÓGICA DE NEGÓCIOS do DB
        if response_data.get("status") == "user_not_found":
            # Retorna 200/mensagem genérica por segurança (ver ponto 4 abaixo)
            pass 
        elif response_data.get("status") == "recovery_started":
            user_id = UUID(response_data.get("user_id"))
            
            # 2. Gerar o PIN em texto plano e o seu hash no backend (Python)
            plain_pin = generate_pin_code()
            pin_hash = hash_pin_code(plain_pin)

            # 3. Chamar a nova função API do DB para salvar o hash do PIN
            raw_result_pin = await db.fetchval(
                "SELECT api.create_pin_recovery_token_api($1, $2)",
                user_id,
                pin_hash
            )
            
            # Se o DB retornar NULO ou status de ERRO ao salvar o PIN (ERRO INTERNO)
            if raw_result_pin is None:
                 logger.error(f"Erro fatal do DB ao salvar PIN para user_id: {user_id}. Resultado nulo.")
                 raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Erro interno do servidor. Falha ao registrar o código de recuperação."
                )

            # ERRO LÓGICO DE DENTRO DO DB (ex: se a função interna falhar por alguma razão)
            pin_response = json.loads(raw_result_pin)
            if pin_response.get("status") != "success":
                logger.error(f"Erro de lógica do DB ao salvar PIN para user_id: {user_id}. Detalhe: {pin_response}")
                
                # AQUI DEVE SER ERRO 500, POIS É UMA FALHA INTERNA QUE NÃO DEVERIA ACONTECER
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Erro ao criar o código de recuperação. Por favor, tente novamente."
                )

            # 4. Enviar o email com o PIN em texto plano (tarefa em background)
            background_tasks.add_task(send_pin_recovery_email, user_email.email, plain_pin)
        else:
            # Outros status inesperados do DB = ERRO INTERNO GRAVE
            logger.error(f"Erro inesperado do DB no fluxo de recuperação de PIN: {response_data}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro inesperado no servidor."
            )

    except HTTPException:
        # Re-lança as exceções HTTP que foram explicitamente levantadas (ex: o 500 acima)
        raise
    except Exception as e:
        # Captura qualquer outra exceção Python inesperada (problema de JSON, de rede, etc.)
        logger.error(f"Erro inesperado no fluxo de recuperação de PIN: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno inesperado do servidor."
        )
    
    # 5. RESPOSTA GENÉRICA E SEGURA:
    # Retorna uma resposta 200 (OK) com uma mensagem genérica, independentemente de o e-mail existir ou não.
    # Isto impede que utilizadores mal-intencionados enumerem e-mails válidos.
    return {"message": "Se uma conta com este e-mail existir, um código de recuperação foi enviado."}

@router.post("/verify-recovery-token")
async def verify_recovery_token(request: VerifyRecoveryTokenRequest, db: asyncpg.Connection = Depends(get_db_connection)):
    """
    Verifica se o token de recuperação é válido usando bcrypt.
    """
    try:
        # 1. Chamar a nova função API do DB para obter o hash e a data de expiração
        raw_result = await db.fetchval(
            "SELECT api.get_pin_recovery_data_api($1)",
            request.email
        )

        if raw_result is None:
            # Resposta genérica para evitar revelar se o e-mail existe
            return {"message": "Invalid or expired token."}

        response_data = json.loads(raw_result)
        
        # 2. Verificar se o resultado do DB é válido
        if response_data.get("status") == "not_found" or response_data.get("status") == "db_error":
             return {"message": "Invalid or expired token."}

        token_hash = response_data.get("token_hash")
        expires_at = response_data.get("expires_at")

        # 3. Verificar a expiração do token no backend (Python)
        expires_at_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expires_at_dt < datetime.now(timezone.utc):
            return {"message": "Invalid or expired token."}

        # 4. Usar bcrypt para comparar o token fornecido com o hash armazenado
        # O bcrypt.checkpw() é seguro contra ataques de tempo.
        if bcrypt.checkpw(request.token.encode('utf-8'), token_hash.encode('utf-8')):
            # Se a verificação for um sucesso, podemos buscar o user_id e retornar
            # Você precisará de uma nova função DB para buscar o ID do usuário por e-mail,
            # já que o fluxo de verificação agora é diferente. Por enquanto, podemos simular.
            user_info = await db.fetchval("SELECT api.find_active_user_by_email($1)", request.email)
            user_id = json.loads(user_info)['user_id']
            return {"message": "Token verified successfully.", "user_id": user_id}
        else:
            return {"message": "Invalid or expired token."}

    except Exception as e:
        logger.error(f"Error in token verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno inesperado do servidor."
        )
