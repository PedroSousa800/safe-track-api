# app/schemas/email.py
from typing import List, Optional
from pydantic import BaseModel, EmailStr

class EmailRecipient(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class EmailSender(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class EmailPayload(BaseModel):
    subject: str
    html: str
    text: Optional[str] = None
    from_: EmailSender
    to: List[EmailRecipient]