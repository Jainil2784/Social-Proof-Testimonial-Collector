from datetime import datetime
import re
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Slug regex pattern: lowercase alphanumeric with single hyphens, no leading/trailing hyphen
SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_and_normalize_slug(v: str) -> str:
    """
    Normalizes slug to lowercase and verifies strict slug formatting.
    """
    if not v:
        raise ValueError("Slug cannot be empty.")
    normalized = v.lower().strip()
    if not SLUG_REGEX.match(normalized):
        raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens (e.g. 'my-company'). No spaces or special characters allowed.")
    return normalized


class CustomQuestionItem(BaseModel):
    question: str = Field(..., min_length=1, max_length=250, description="Custom question for testimonial submitters")

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Question text cannot be blank.")
        return cleaned


class SpaceBase(BaseModel):
    name: str
    slug: str
    custom_prompt: Optional[str] = None
    logo_url: Optional[str] = None
    avatar_enabled: bool = True
    rating_enabled: bool = True
    custom_questions: List[CustomQuestionItem] = []


class SpaceCreate(SpaceBase):
    owner_id: str


class SpaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Space/Business Name")
    slug: str = Field(..., description="Unique URL slug (e.g. abc-technologies)")
    custom_prompt: Optional[str] = Field(None, max_length=500, description="Prompt shown to customers submitting reviews")
    logo_url: Optional[str] = Field(None, description="URL or relative path to space logo image")
    avatar_enabled: bool = Field(True, description="Enable customer avatar upload option")
    rating_enabled: bool = Field(True, description="Enable star rating submission")
    custom_questions: List[CustomQuestionItem] = Field(default_factory=list, max_length=10, description="Up to 10 custom questions")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Space name cannot be blank.")
        return cleaned

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        return validate_and_normalize_slug(v)


class SpaceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None)
    custom_prompt: Optional[str] = Field(None, max_length=500)
    logo_url: Optional[str] = Field(None)
    avatar_enabled: Optional[bool] = Field(None)
    rating_enabled: Optional[bool] = Field(None)
    custom_questions: Optional[List[CustomQuestionItem]] = Field(None, max_length=10)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Space name cannot be blank.")
            return cleaned
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_and_normalize_slug(v)
        return v


class SpaceResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    slug: str
    custom_prompt: Optional[str] = None
    logo_url: Optional[str] = None
    avatar_enabled: bool = True
    rating_enabled: bool = True
    custom_questions: List[CustomQuestionItem] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicSpaceResponse(BaseModel):
    name: str
    slug: str
    custom_prompt: Optional[str] = None
    logo_url: Optional[str] = None
    avatar_enabled: bool = True
    rating_enabled: bool = True
    custom_questions: List[CustomQuestionItem] = []

    model_config = ConfigDict(from_attributes=True)
