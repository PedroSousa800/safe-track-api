from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
import asyncpg
import os
from dotenv import load_dotenv
import json # Adicione esta importação no topo do arquivo

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

app = FastAPI()

# --- Configuração do Banco de Dados ---
DATABASE_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

# Pool de conexões (melhor para performance em aplicações web)
db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        print("Conexão com o banco de dados estabelecida com sucesso!")
    except Exception as e:
        print(f"Falha ao conectar ao banco de dados: {e}")
        # Em um ambiente de produção, você pode querer levantar uma exceção aqui
        # para impedir o início da aplicação se a conexão com o DB for crítica.

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()
        print("Conexão com o banco de dados encerrada.")

# Dependência para obter uma conexão do pool
async def get_db_connection():
    if db_pool is None:
        raise HTTPException(status_code=500, detail="Database pool not initialized.")
    async with db_pool.acquire() as connection:
        yield connection

# --- Modelos Pydantic para validação de entrada ---

class UserRegister(BaseModel):
    email: EmailStr
    password: str # Será usado apenas para o registro inicial no backend, hashado e descartado
    # FastAPI pode validar o tamanho da senha aqui se necessário, mas o DB também fará o hash.

class UserFinalizePin(BaseModel):
    user_id: str # Para simplicidade, string, mas pode ser UUID
    pin: str

class UserLogin(BaseModel):
    email: EmailStr
    pin: str

# --- Endpoints da API ---

@app.get("/")
async def read_root():
    return {"message": "Bem-vindo ao SafeTrack API!"}

# Endpoint de Registro
@app.post("/register")
async def register_user(user_data: UserRegister, db: asyncpg.Connection = Depends(get_db_connection)):
    try:
        # A chamada à função do DB já trata o hash da senha
        # asyncpg.fetchval retorna o valor da primeira coluna.
        # Se a função do DB retorna JSONB, asyncpg deveria converter para dict Python.
        # Mas se estiver vindo como string, vamos parsear:
        raw_result = await db.fetchval( # Renomeado para 'raw_result' para clareza
            "SELECT api.register_user_api($1::jsonb)",
            user_data.model_dump_json() # Converte o modelo Pydantic para JSON string
        )

        # Tentar parsear o resultado se não for um dicionário (já que o erro sugere que é uma string)
        if isinstance(raw_result, str):
            result_dict = json.loads(raw_result)
        else:
            result_dict = raw_result # Já é um dicionário ou similar

        return {"message": result_dict['message'], "user_id": result_dict['user_id']}
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
        # Tentar parsear o resultado se não for um dicionário (já que o erro sugere que é uma string)
        if isinstance(raw_result, str):
            result_dict = json.loads(raw_result)
        else:
            result_dict = raw_result # Já é um dicionário ou similar
        return {"message": result_dict['message'], "user_id": result_dict['user_id']}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# Endpoint de Login
@app.post("/login")
async def login_user(credentials: UserLogin, db: asyncpg.Connection = Depends(get_db_connection)):
    try:
        raw_result = await db.fetchval (
            "SELECT api.login_user_api($1::jsonb)",
            credentials.model_dump_json()
        )
        # Tentar parsear o resultado se não for um dicionário (já que o erro sugere que é uma string)
        if isinstance(raw_result, str):
            result_dict = json.loads(raw_result)
        else:
            result_dict = raw_result # Já é um dicionário ou similar

        # Se login_user_api retorna um JSONB com 'user_id', é sucesso
        return {"message": result_dict['message'], "user_id": result_dict['user_id']}
    
    except Exception as e:
        # As exceções do DB (Invalid email/PIN, inactive) virão como HTTPException
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

