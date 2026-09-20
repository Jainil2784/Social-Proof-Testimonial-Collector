from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ─── Requests ────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)



class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)


# ─── Responses ───────────────────────────────────────────────────────────────

class AuthUserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    is_email_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegisterResponse(BaseModel):
    message: str
    user: AuthUserResponse
    # dev_verification_token intentionally removed — never exposed to frontend


class ForgotPasswordResponse(BaseModel):
    message: str
    # dev_reset_token intentionally removed — sent via email only


class MessageResponse(BaseModel):
    message: str


class ResendVerificationResponse(BaseModel):
    message: str
    cooldown_seconds_remaining: Optional[int] = None  # set when rate-limited
