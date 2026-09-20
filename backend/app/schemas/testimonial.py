from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from backend.app.models.testimonial import TestimonialCustomAnswer, TestimonialStatus


class TestimonialBase(BaseModel):
    __test__ = False
    client_name: str
    client_email: EmailStr
    company_role: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    review_text: str
    avatar_url: Optional[str] = None
    custom_answers: List[TestimonialCustomAnswer] = []
    status: str = TestimonialStatus.PENDING.value
    is_featured: bool = False


class TestimonialCreate(TestimonialBase):
    __test__ = False
    space_id: str


class TestimonialPublicSubmissionResponse(BaseModel):
    __test__ = False
    message: str = "Thank you! Your testimonial has been submitted and is awaiting review."


class TestimonialResponse(TestimonialBase):
    __test__ = False
    id: str
    space_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestimonialStatusUpdateRequest(BaseModel):
    __test__ = False
    status: str

    def get_normalized_status(self) -> str:
        val = self.status.lower().strip()
        allowed = {s.value for s in TestimonialStatus}
        if val not in allowed:
            raise ValueError(f"Invalid status '{self.status}'. Allowed values are: {', '.join(sorted(allowed))}")
        return val


class TestimonialFeaturedUpdateRequest(BaseModel):
    __test__ = False
    is_featured: bool


class TestimonialModerationResponse(BaseModel):
    __test__ = False
    id: str
    space_id: str
    space_name: str
    space_slug: str
    client_name: str
    client_email: str
    company_role: Optional[str] = None
    rating: Optional[int] = None
    review_text: str
    avatar_url: Optional[str] = None
    custom_answers: List[TestimonialCustomAnswer] = []
    status: str
    is_featured: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestimonialPaginationResponse(BaseModel):
    __test__ = False
    items: List[TestimonialModerationResponse]
    page: int
    limit: int
    total: int
    pages: int


class TestimonialStatsResponse(BaseModel):
    __test__ = False
    total_spaces: int
    total_reviews: int
    pending_reviews: int
    approved_reviews: int
    rejected_reviews: int
    archived_reviews: int
    featured_reviews: int


class WallTestimonialItem(BaseModel):
    __test__ = False
    id: str
    client_name: str
    company_role: Optional[str] = None
    rating: Optional[int] = None
    review_text: str
    avatar_url: Optional[str] = None
    is_featured: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WallSpaceInfo(BaseModel):
    __test__ = False
    name: str
    slug: str
    logo_url: Optional[str] = None
    custom_prompt: Optional[str] = None
    rating_enabled: bool = True
    avatar_enabled: bool = True


class WallOfLoveResponse(BaseModel):
    __test__ = False
    space: WallSpaceInfo
    testimonials: List[WallTestimonialItem]


class StarDistribution(BaseModel):
    """Star distribution: keys are '1' through '5', values are counts."""
    __test__ = False
    star_1: int = 0
    star_2: int = 0
    star_3: int = 0
    star_4: int = 0
    star_5: int = 0


class StatusDistribution(BaseModel):
    __test__ = False
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    archived: int = 0


class AnalyticsResponse(BaseModel):
    __test__ = False
    # Scope metadata
    scope: str  # "all" or space_id
    space_name: Optional[str] = None  # set when scoped to a single space

    # Counts
    total_reviews: int = 0
    featured_reviews: int = 0
    total_spaces: int = 0

    # Rating
    average_rating: Optional[float] = None  # None when no rated reviews

    # Distributions
    star_distribution: StarDistribution = StarDistribution()
    status_distribution: StatusDistribution = StatusDistribution()


class EmbedResponse(BaseModel):
    __test__ = False
    space: WallSpaceInfo
    embed_type: str = "grid"
    total_approved: int = 0
    average_rating: Optional[float] = None
    testimonials: List[WallTestimonialItem] = []


