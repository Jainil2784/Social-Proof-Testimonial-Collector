import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from bson import ObjectId
from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from backend.app.db.mongodb import get_spaces_collection, get_testimonials_collection
from backend.app.models.testimonial import TestimonialStatus
from backend.app.schemas.space import validate_and_normalize_slug
from backend.app.schemas.testimonial import (
    EmbedResponse,
    TestimonialPublicSubmissionResponse,
    WallOfLoveResponse,
    WallSpaceInfo,
    WallTestimonialItem,
)

router = APIRouter(prefix="/api/public", tags=["Public Testimonials"])

# Testimonial Upload directory setup
TESTIMONIAL_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "testimonials"
)
os.makedirs(TESTIMONIAL_UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB Limit


@router.post(
    "/spaces/{space_slug}/testimonials",
    response_model=TestimonialPublicSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_public_testimonial(
    space_slug: str,
    client_name: str = Form(...),
    client_email: str = Form(...),
    review_text: str = Form(...),
    company_role: Optional[str] = Form(None),
    rating: Optional[int] = Form(None),
    custom_answers: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
):
    """
    Public endpoint for customers to submit a testimonial to a Space by slug.
    No authentication required.
    Status is strictly set to 'pending' and is_featured is set to False server-side.
    """
    slug_clean = validate_and_normalize_slug(space_slug)
    spaces_coll = get_spaces_collection()

    space_doc = await spaces_coll.find_one({"slug": slug_clean})
    if not space_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found."
        )

    # 1. Validate Client Name
    name_clean = client_name.strip()
    if not name_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client name cannot be blank."
        )
    if len(name_clean) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client name must not exceed 100 characters."
        )

    # 2. Validate Email
    email_clean = client_email.strip().lower()
    try:
        valid_email_obj = validate_email(email_clean, check_deliverability=False)
        email_clean = valid_email_obj.normalized
    except EmailNotValidError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid email address: {str(e)}"
        )

    # 3. Validate Review Text
    review_clean = review_text.strip()
    if not review_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review text cannot be blank."
        )
    if len(review_clean) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review text must be at least 10 characters long."
        )
    if len(review_clean) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review text must not exceed 2000 characters."
        )

    # 4. Validate Company Role
    role_clean = company_role.strip() if company_role else None
    if role_clean and len(role_clean) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company role must not exceed 100 characters."
        )

    # 5. Respect Space Settings: Rating
    rating_enabled = space_doc.get("rating_enabled", True)
    final_rating: Optional[int] = None
    if rating_enabled:
        if rating is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Star rating is required for this Space."
            )
        if not (1 <= rating <= 5):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rating must be an integer between 1 and 5."
            )
        final_rating = rating
    else:
        final_rating = None  # Do not store a rating if disabled

    # 6. Respect Space Settings & Upload Avatar
    avatar_enabled = space_doc.get("avatar_enabled", True)
    avatar_url: Optional[str] = None

    if avatar_enabled and avatar and avatar.filename:
        content_type = avatar.content_type.lower() if avatar.content_type else ""
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid image type '{content_type}'. Allowed formats: JPEG, PNG, WebP, GIF, SVG."
            )

        contents = await avatar.read()
        if len(contents) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Avatar image size exceeds the 2MB limit."
            )

        # Generate safe filename and path traversal protection
        ext = ALLOWED_IMAGE_TYPES[content_type]
        safe_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(TESTIMONIAL_UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as f:
            f.write(contents)

        avatar_url = f"/uploads/testimonials/{safe_filename}"

    # 7. Process Custom Answers
    parsed_custom_answers = []
    if custom_answers:
        try:
            if isinstance(custom_answers, str):
                parsed = json.loads(custom_answers)
            else:
                parsed = custom_answers
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "question" in item and "answer" in item:
                        parsed_custom_answers.append({
                            "question": str(item["question"]).strip()[:250],
                            "answer": str(item["answer"]).strip()[:500]
                        })
        except Exception:
            pass  # Fail gracefully if custom answers format is bad

    # 8. Construct & Persist Testimonial Document
    now = datetime.now(timezone.utc)
    space_id_val = str(space_doc["_id"])

    testimonial_doc = {
        "space_id": space_id_val,
        "client_name": name_clean,
        "client_email": email_clean,
        "company_role": role_clean,
        "rating": final_rating,
        "review_text": review_clean,
        "avatar_url": avatar_url,
        "custom_answers": parsed_custom_answers,
        "status": TestimonialStatus.PENDING.value,  # Server-enforced moderation state
        "is_featured": False,                         # Server-enforced moderation state
        "created_at": now,
        "updated_at": now
    }

    testimonials_coll = get_testimonials_collection()
    await testimonials_coll.insert_one(testimonial_doc)

    return TestimonialPublicSubmissionResponse(
        message="Thank you! Your testimonial has been submitted and is awaiting review."
    )


@router.get(
    "/spaces/{space_slug}/wall",
    response_model=WallOfLoveResponse,
    status_code=status.HTTP_200_OK,
)
async def get_public_wall_of_love(space_slug: str):
    """
    Public Wall of Love API for a Space.
    Returns safe Space details and all approved testimonials, ordered newest first.
    Excludes client_email and owner_id.
    Respects rating_enabled and avatar_enabled settings.
    No authentication required.
    """
    space_slug_clean = space_slug.strip().lower()
    spaces_coll = get_spaces_collection()
    space_doc = await spaces_coll.find_one({"slug": space_slug_clean})

    if not space_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found."
        )

    # Respect Space settings
    rating_enabled = bool(space_doc.get("rating_enabled", True))
    avatar_enabled = bool(space_doc.get("avatar_enabled", True))

    wall_space = WallSpaceInfo(
        name=space_doc.get("name", ""),
        slug=space_doc.get("slug", space_slug_clean),
        logo_url=space_doc.get("logo_url"),
        custom_prompt=space_doc.get("custom_prompt"),
        rating_enabled=rating_enabled,
        avatar_enabled=avatar_enabled,
    )

    space_id_val = str(space_doc["_id"])
    testimonials_coll = get_testimonials_collection()

    query = {
        "space_id": {"$in": [space_id_val, space_doc["_id"]]},
        "status": TestimonialStatus.APPROVED.value,
    }

    cursor = testimonials_coll.find(query).sort("created_at", -1)
    wall_testimonials = []

    async for doc in cursor:
        doc_rating = doc.get("rating") if rating_enabled else None
        doc_avatar = doc.get("avatar_url") if avatar_enabled else None

        wall_testimonials.append(
            WallTestimonialItem(
                id=str(doc.get("_id", "")),
                client_name=doc.get("client_name", ""),
                company_role=doc.get("company_role"),
                rating=doc_rating,
                review_text=doc.get("review_text", ""),
                avatar_url=doc_avatar,
                is_featured=bool(doc.get("is_featured", False)),
                created_at=doc.get("created_at") or datetime.now(timezone.utc),
            )
        )

    return WallOfLoveResponse(
        space=wall_space,
        testimonials=wall_testimonials,
    )


@router.get(
    "/spaces/{space_slug}/embed",
    response_model=EmbedResponse,
    status_code=status.HTTP_200_OK,
)
async def get_public_embed_data(
    space_slug: str,
    type: Optional[str] = Query("grid", description="Embed layout type: grid, carousel, badge")
):
    """
    Public Embed API for external websites and iframes.
    Returns safe Space details and approved testimonials.
    Calculates total_approved and average_rating for badge mode.
    Excludes client_email and owner_id.
    No authentication required.
    """
    space_slug_clean = space_slug.strip().lower()
    spaces_coll = get_spaces_collection()
    space_doc = await spaces_coll.find_one({"slug": space_slug_clean})

    if not space_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found."
        )

    # Normalize embed type
    allowed_types = {"grid", "carousel", "badge"}
    embed_type_clean = (type or "grid").strip().lower()
    if embed_type_clean not in allowed_types:
        embed_type_clean = "grid"

    rating_enabled = bool(space_doc.get("rating_enabled", True))
    avatar_enabled = bool(space_doc.get("avatar_enabled", True))

    wall_space = WallSpaceInfo(
        name=space_doc.get("name", ""),
        slug=space_doc.get("slug", space_slug_clean),
        logo_url=space_doc.get("logo_url"),
        custom_prompt=space_doc.get("custom_prompt"),
        rating_enabled=rating_enabled,
        avatar_enabled=avatar_enabled,
    )

    space_id_val = str(space_doc["_id"])
    testimonials_coll = get_testimonials_collection()

    query = {
        "space_id": {"$in": [space_id_val, space_doc["_id"]]},
        "status": TestimonialStatus.APPROVED.value,
    }

    cursor = testimonials_coll.find(query).sort("created_at", -1)
    wall_testimonials = []
    rating_sum = 0
    rating_count = 0

    async for doc in cursor:
        doc_rating = doc.get("rating") if rating_enabled else None
        doc_avatar = doc.get("avatar_url") if avatar_enabled else None

        raw_rating = doc.get("rating")
        if raw_rating and isinstance(raw_rating, int) and 1 <= raw_rating <= 5:
            rating_sum += raw_rating
            rating_count += 1

        wall_testimonials.append(
            WallTestimonialItem(
                id=str(doc.get("_id", "")),
                client_name=doc.get("client_name", ""),
                company_role=doc.get("company_role"),
                rating=doc_rating,
                review_text=doc.get("review_text", ""),
                avatar_url=doc_avatar,
                is_featured=bool(doc.get("is_featured", False)),
                created_at=doc.get("created_at") or datetime.now(timezone.utc),
            )
        )

    avg_rating = round(rating_sum / rating_count, 1) if rating_count > 0 else None

    return EmbedResponse(
        space=wall_space,
        embed_type=embed_type_clean,
        total_approved=len(wall_testimonials),
        average_rating=avg_rating,
        testimonials=wall_testimonials,
    )


