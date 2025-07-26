# main.py

from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field
import asyncpg
import os
from dotenv import load_dotenv
import json
from uuid import UUID
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

app = FastAPI()

# --- Configuração do Banco de Dados ---
DATABASE_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

# Pool de conexões
db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        print("Conexão com o banco de dados estabelecida com sucesso!")
    except Exception as e:
        print(f"Falha ao conectar ao banco de dados: {e}")

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()
        print("Conexão com o banco de dados encerrada.")

# Dependência para obter uma conexão do pool
async def get_db_connection():
    if db_pool is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database pool not initialized.")
    async with db_pool.acquire() as connection:
        yield connection

# --- Modelos Pydantic para validação de entrada ---

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    username: str

class UserFinalizePin(BaseModel):
    user_id: str # Mantido como str para corresponder ao que vem do frontend
    pin: str

class UserProfileUpdate(BaseModel):
    profile_type: str = Field(..., example="tutor", pattern="^(tutor|monitorado)$") # Garante validação no FastAPI

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
        raw_result = await db.fetchval(
            "SELECT api.register_user_api($1::jsonb)",
            user_data.model_dump_json()
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
                    "user_id": pin_data.user_id,
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
        print(f"Erro inesperado no login: {e}") 
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