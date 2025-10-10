# app/schemas/user.py
# Este ficheiro contém todos os schemas Pydantic para o projeto SafeTrack,
# corrigidos e verificados para incluir todas as classes necessárias.

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class UserBase(BaseModel):
    """
    Schema base para os atributos de um usuário.
    """
    email: EmailStr
    
class UserCreate(UserBase):
    """
    Schema para a criação de um novo usuário.
    Espera-se que 'name', 'email' e 'password' sejam fornecidos no corpo da requisição.
    """
    name: Optional[str] = None
    password: str

class UserEmail(BaseModel):
    """
    Schema para validação do email.
    """
    email: EmailStr

class UserLogin(BaseModel):
    """
    Schema para autenticação do usuário.
    """
    password: str

class UserFinalizePin(BaseModel):
    """
    Schema para finalização do registro com o PIN.
    """
    user_id: UUID
    pin: str

class LocationUpdate(BaseModel):
    """
    Schema para o registo de dados de localização.
    
    O campo 'timestamp' é OBRIGATÓRIO e deve ser fornecido
    pelo cliente com o offset de fuso horário (e.g., ISO 8601 com +01:00)
    para garantir que a API possa calcular corretamente o UTC e o fuso horário local.
    """
    latitude: float = Field(..., description="Latitude do dispositivo.")
    longitude: float = Field(..., description="Longitude do dispositivo.")
    # Removido o default_factory e Optional para forçar o cliente a enviar um timestamp aware.
    timestamp: datetime = Field(..., description="Timestamp de coleta da localização, deve incluir o fuso horário (e.g., 2025-10-06T10:30:00+01:00).")

class LocationIntervalUpdate(BaseModel):
    """
    Schema para atualizar o intervalo de atualização de localização de um usuário.
    """
    interval_in_seconds: int = Field(..., ge=10, description="Intervalo de atualização em segundos (mínimo de 10 segundos).")


class UserProfileUpdate(BaseModel):
    profile_type: str = Field(..., description="Type of user. For example: 'T' or 'M'")

class Token(BaseModel):
    """
    Schema para o token de autenticação.
    """
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """
    Schema para os dados do token JWT.
    """
    email: Optional[str] = None

class VerifyRecoveryTokenRequest(BaseModel):
    """
    Schema para verificar o token de recuperação de senha.
    """
    email: str
    token: str    
