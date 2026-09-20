from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SpaceModel(BaseModel):
    """
    MongoDB Pydantic model for Spaces (Testimonial collection pages).
    """
    id: Optional[str] = Field(default=None, alias="_id")
    owner_id: str
    name: str
    slug: str
    custom_prompt: Optional[str] = None
    logo_url: Optional[str] = None
    avatar_enabled: bool = True
    rating_enabled: bool = True
    custom_questions: List[Any] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )
