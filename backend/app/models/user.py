from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserModel(BaseModel):
    """
    MongoDB Pydantic model for Users (Business Owners).
    """
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    email: EmailStr
    password_hash: str
    is_active: bool = True
    is_email_verified: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )
