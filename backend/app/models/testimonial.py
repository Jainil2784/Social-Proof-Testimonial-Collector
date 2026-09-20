import enum
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TestimonialStatus(str, enum.Enum):
    __test__ = False
    PENDING = "pending"
    APPROVED = "approved"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class TestimonialCustomAnswer(BaseModel):
    __test__ = False
    question: str
    answer: str


class TestimonialModel(BaseModel):
    """
    MongoDB Pydantic model for Testimonials.
    """
    __test__ = False
    id: Optional[str] = Field(default=None, alias="_id")
    space_id: str
    client_name: str
    client_email: EmailStr
    company_role: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    review_text: str
    avatar_url: Optional[str] = None
    custom_answers: List[TestimonialCustomAnswer] = Field(default_factory=list)
    status: str = TestimonialStatus.PENDING.value
    is_featured: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )
