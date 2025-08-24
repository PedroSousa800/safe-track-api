# models.py
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional
from uuid import UUID

# --- Modelos Pydantic para os Endpoints ---

class UserEmail(BaseModel):
    email: EmailStr = Field(..., title="Email do Usuário", description="Endereço de e-mail do usuário para login ou recuperação.")

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=3, max_length=50)

class UserFinalizePin(BaseModel):
    user_id: UUID
    pin: str = Field(min_length=4, max_length=4)

class UserProfileUpdate(BaseModel):
    profile_type: str = Field(..., description="O novo tipo de perfil para o usuário (e.g., 'driver' ou 'guardian')")

class VerifyRecoveryTokenRequest(BaseModel):
    email: EmailStr
    token: str

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    accuracy: float
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)

class LocationIntervalUpdate(BaseModel):
    interval_in_seconds: int = Field(..., gt=0, description="O novo intervalo de tempo em segundos para a atualização de localização.")
