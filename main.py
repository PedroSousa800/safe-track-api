# main.py

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field
import asyncpg
import os
from dotenv import load_dotenv
import json
from uuid import UUID
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
# Importe os modelos que você definiu para os endpoints
from models import UserEmail, UserRegister, UserFinalizePin, UserProfileUpdate, VerifyRecoveryTokenRequest
import random
import string
import logging
import secrets
# Importar a biblioteca bcrypt
from passlib.context import CryptContext

# Defina a validade do token (ex: 15 minutos)
TOKEN_EXPIRATION_MINUTES = 15

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- Configuração do Banco de Dados ---
DATABASE_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

# Pool de conexões
db_pool = None

# Contexto de hash para senhas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Função para criar o hash da senha
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

@app.on_event("startup")
async def startup():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        logger.info("Conexão com o banco de dados estabelecida com sucesso!")
    except Exception as e:
        logger.error(f"Falha ao conectar ao banco de dados: {e}")

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()
        logger.info("Conexão com o banco de dados encerrada.")

# Dependência para obter uma conexão do pool
async def get_db_connection():
    if db_pool is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database pool not initialized.")
    async with db_pool.acquire() as connection:
        yield connection

# --- JWT: Configurações de JWT ---
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY not set in environment variables.")

# JWT: Esquema de autenticação OAuth2 (para extrair o token do header Authorization)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# JWT: Função para criar o token de acesso
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

# JWT: Função para obter o user_id do token (dependência de autenticação)
async def get_current_user_id(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub") # 'sub' é geralmente uma string
        if user_id is None:
            raise credentials_exception
        return user_id # Retorna o user_id como string
    except JWTError:
        raise credentials_exception

# --- Endpoints da API ---

@app.get("/")
async def read_root():
    return {"message": "Bem-vindo ao SafeTrack API!"}

# Endpoint de Registro
@app.post("/register", status_code=status.HTTP_200_OK)
async def register_user(user_data: UserRegister, db: asyncpg.Connection = Depends(get_db_connection)):
    try:
        # Hash da senha antes de enviar para o banco de dados
        hashed_password = get_password_hash(user_data.password)
        # Atualizar o dicionário com o hash da senha
        payload = {
            "email": user_data.email,
            "name": user_data.name,
            "password_hash": hashed_password # Usar o hash da senha
        }
        
        raw_result = await db.fetchval(
            "SELECT api.register_user_api($1::jsonb)",
            json.dumps(payload) # Enviar o payload com o hash
        )

        if isinstance(raw_result, str):
            result_dict = json.loads(raw_result)
        else:
            result_dict = raw_result

        if result_dict.get('status') == 'new_user_registered':
            return {
                "message": result_dict['message'],
                "user_id": result_dict['user_id'],
                "status": result_dict['status']
            }
        elif result_dict.get('status') == 'pending_pin_exists':
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "User already exists and is pending PIN. Please finalize your registration.",
                    "user_id": result_dict['user_id'],
                    "status": result_dict['status']
                }
            )
        elif result_dict.get('status') == 'active':
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Email already registered and active.",
                    "user_id": result_dict['user_id'],
                    "status": result_dict['status']
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result_dict.get('message', 'Failed to register user due to unknown status from DB.')
            )

    except HTTPException:
        raise
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
# Endpoint para Finalizar Registro com PIN
@app.post("/finalize-pin")
async def finalize_pin(pin_data: UserFinalizePin, db: asyncpg.Connection = Depends(get_db_connection)):
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
                    "user_id": str(pin_data.user_id), # <-- CORRIGIDO AQUI: Converte UUID para string
                    "status": result_dict.get('status', 'error')
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# Endpoint de Login (AGORA USA OAuth2PasswordRequestForm e retorna profile_type)
@app.post("/login")
async def login_user(form_data: OAuth2PasswordRequestForm = Depends(), db: asyncpg.Connection = Depends(get_db_connection)):
    try:
        # Use form_data.username para o email e form_data.password para o PIN
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
            
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": user_id_from_db}, expires_delta=access_token_expires
            )
            
            # Adicione o profile_type à resposta do login
            return {
                "message": result_dict['message'],
                "user_id": user_id_from_db,
                "profile_type": result_dict.get('profile_type'), # Adicionado profile_type
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
        # Registre o erro para depuração
        logger.error(f"Erro inesperado no login: {e}") 
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

# Endpoint para atualizar o tipo de perfil do usuário (CORRIGIDO: PATCH e URL)
@app.patch("/users/{user_id}/profile_type", status_code=status.HTTP_200_OK) # <-- ALTERADO AQUI
async def update_user_profile(
    user_id: UUID, # FastAPI converte automaticamente de string da URL para UUID
    profile_data: UserProfileUpdate,
    db: asyncpg.Connection = Depends(get_db_connection),
    current_user_id: str = Depends(get_current_user_id) # Retorna user_id como str do JWT
):
    # Converte current_user_id para UUID para comparação consistente
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "Database error during profile update.", "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "An unexpected error occurred.", "error": str(e)})


# ----------------- Funcionalidade de Recuperação de PIN -----------------
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

@app.post("/auth/recover-pin", status_code=status.HTTP_200_OK)
async def recover_pin(user_email: UserEmail, background_tasks: BackgroundTasks, db: asyncpg.Connection = Depends(get_db_connection)):
    """
    Endpoint para iniciar o processo de recuperação de PIN.
    - Chama a função do schema `api` para orquestrar o processo.
    - Em caso de sucesso, envia um e-mail com o código em uma tarefa em background.
    - CORRIGIDO: Sempre retorna um status 200 para evitar enumeração de usuários.
    """
    try:
        # Chama a função do schema API, que encapsula toda a lógica do DB
        raw_result = await db.fetchval(
            "SELECT api.start_pin_recovery_process_api_func($1)",
            user_email.email
        )
        
        # O backend não retorna um erro se o email não for encontrado por segurança.
        # Ele apenas não envia o email.
        # Por isso, sempre retornamos um status 200.
        if raw_result is not None:
            response_data = json.loads(raw_result)
            if response_data.get("status") == "recovery_started":
                token = response_data.get("token")
                if token:
                    # Enviar o e-mail em uma tarefa em background
                    background_tasks.add_task(send_pin_recovery_email, user_email.email, token)
            # Se a resposta do DB for inválida, logamos mas ainda retornamos um sucesso genérico
            else:
                logger.error(f"Erro inesperado do DB no fluxo de recuperação de PIN: {response_data}")

    except Exception as e:
        logger.error(f"Unexpected error in PIN recovery flow: {e}")
    # Sempre retorna um sucesso genérico para o frontend, conforme a lógica de segurança.
    return {"message": "If an account with that email exists, a recovery code has been sent."}


@app.post("/auth/verify-recovery-token")
async def verify_recovery_token(request: VerifyRecoveryTokenRequest, db: asyncpg.Connection = Depends(get_db_connection)):
    """
    Verifica se o token de recuperação fornecido é válido e ainda não expirou.
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
            # Em caso de falha, retorne uma mensagem genérica por segurança
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
