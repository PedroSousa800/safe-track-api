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
    Schema para a atualização de dados de localização.
    """
    latitude: float
    longitude: float
    accuracy: float
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)

class LocationIntervalUpdate(BaseModel):
    """
    Schema para a atualização do intervalo de localização.
    """
    latitude: float
    longitude: float

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
