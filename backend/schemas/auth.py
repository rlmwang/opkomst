from datetime import datetime

from pydantic import BaseModel, Field

from .common import LowercaseEmail


class RegisterRequest(BaseModel):
    email: LowercaseEmail
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: LowercaseEmail
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    email_verified_at: datetime | None
    is_approved: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class VerifyEmailRequest(BaseModel):
    token: str


class AuthResponse(BaseModel):
    token: str
    user: UserOut
