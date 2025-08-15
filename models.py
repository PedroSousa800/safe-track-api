# models.py
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID

class UserEmail(BaseModel):
    email: EmailStr

class UserRegister(BaseModel):
    email: EmailStr
    password: str 
    name: str

class UserFinalizePin(BaseModel):
    user_id: UUID
    pin: str = Field(..., min_length=4, max_length=4)

class UserProfileUpdate(BaseModel):
    # O Pydantic irá agora validar se o valor é uma única letra
    # 'T' para 'tutor' ou 'M' para 'monitorado'
    profile_type: str = Field(..., pattern="^[T]$")

# Modelo Pydantic para o corpo da requisição de verificação de token
class VerifyRecoveryTokenRequest(BaseModel):
    email: str
    token: str
