import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do ficheiro .env
load_dotenv()

# Define a classe de configurações usando Pydantic
class Settings(BaseSettings):
    # A URL completa da base de dados, que será lida diretamente do .env
    DATABASE_URL: str

    # Variáveis de ambiente da base de dados
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str

    # Chave secreta e algoritmo para o token JWT.
    # Usamos o nome de variável que está no seu ficheiro .env.
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    
    # O tempo de expiração do token de acesso em minutos.
    ACCESS_TOKEN_EXPIRE_MINUTES: int 

    # Configurações do pool de conexões do asyncpg
    DB_POOL_MIN_SIZE: int 
    DB_POOL_MAX_SIZE: int 
    DB_POOL_TIMEOUT_SECONDS: int 

    # --- Configurações de REDIS ---
    REDIS_URL: str

    # --- Configurações de RATE LIMITING
    LOCATION_RATE_LIMIT_TIMES: int
    LOCATION_RATE_LIMIT_SECONDS: int

    LOG_LEVEL: str

    class Config:
        env_file = ".env"
        # Permite que as variáveis de ambiente sejam lidas de forma insensível a maiúsculas/minúsculas
        # e lê as variáveis 'extras' que o modelo não mapeia explicitamente.
        extra = 'allow'
        case_sensitive = True
        # orm_mode = True  # Alterado em Pydantic V2 para from_attributes
        from_attributes = True

# Cria uma instância da classe Settings.
settings = Settings()
