from datetime import datetime, timezone
import os
import uuid
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from typing import List

from backend.app.core.auth_dependency import get_current_user
from backend.app.db.mongodb import get_spaces_collection, get_testimonials_collection
from backend.app.schemas.auth import MessageResponse
from backend.app.schemas.space import (
    PublicSpaceResponse,
    SpaceCreateRequest,
    SpaceResponse,
    SpaceUpdateRequest,
    validate_and_normalize_slug,
)

router = APIRouter(prefix="/api", tags=["Space Management"])

# Upload directory setup
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "spaces")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB Limit


def parse_object_id(id_str: str) -> ObjectId:
    """Helper to convert string to ObjectId or raise 400 Bad Request."""
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Space ID format."
        )


@router.post("/spaces/upload-logo", status_code=status.HTTP_201_CREATED)
async def upload_space_logo(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a space logo image file (Max 2MB, JPEG/PNG/WebP/GIF/SVG).
    Requires authentication.
    """
    content_type = file.content_type.lower() if file.content_type else ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{content_type}'. Allowed image formats: JPEG, PNG, WebP, GIF, SVG."
        )

    # Read content to check file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the 2MB limit."
        )

    ext = ALLOWED_IMAGE_TYPES[content_type]
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, "wb") as f:
        f.write(contents)

    logo_url = f"/uploads/spaces/{safe_filename}"
    return {"logo_url": logo_url}


@router.post("/spaces", response_model=SpaceResponse, status_code=status.HTTP_201_CREATED)
async def create_space(
    req: SpaceCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new testimonial collection Space.
    Requires authentication. owner_id is strictly bound to current authenticated user.
    """
    slug_clean = validate_and_normalize_slug(req.slug)
    spaces_coll = get_spaces_collection()

    # Verify slug uniqueness
    existing_space = await spaces_coll.find_one({"slug": slug_clean})
    if existing_space:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A Space with this slug already exists."
        )

    now = datetime.now(timezone.utc)
    owner_id_str = current_user["id"]

    space_doc = {
        "owner_id": owner_id_str,
        "name": req.name.strip(),
        "slug": slug_clean,
        "custom_prompt": req.custom_prompt.strip() if req.custom_prompt else None,
        "logo_url": req.logo_url,
        "avatar_enabled": req.avatar_enabled,
        "rating_enabled": req.rating_enabled,
        "custom_questions": [q.model_dump() for q in req.custom_questions],
        "created_at": now,
        "updated_at": now
    }

    result = await spaces_coll.insert_one(space_doc)
    space_id_str = str(result.inserted_id)

    return SpaceResponse(
        id=space_id_str,
        owner_id=owner_id_str,
        name=space_doc["name"],
        slug=space_doc["slug"],
        custom_prompt=space_doc["custom_prompt"],
        logo_url=space_doc["logo_url"],
        avatar_enabled=space_doc["avatar_enabled"],
        rating_enabled=space_doc["rating_enabled"],
        custom_questions=req.custom_questions,
        created_at=now,
        updated_at=now
    )


@router.get("/spaces", response_model=List[SpaceResponse])
async def list_owner_spaces(
    current_user: dict = Depends(get_current_user)
):
    """
    List all Spaces belonging ONLY to the authenticated owner.
    """
    spaces_coll = get_spaces_collection()
    owner_id_str = current_user["id"]

    cursor = spaces_coll.find({"owner_id": owner_id_str}).sort("created_at", -1)
    spaces_list = []

    async for doc in cursor:
        spaces_list.append(SpaceResponse(
            id=str(doc["_id"]),
            owner_id=str(doc["owner_id"]),
            name=doc["name"],
            slug=doc["slug"],
            custom_prompt=doc.get("custom_prompt"),
            logo_url=doc.get("logo_url"),
            avatar_enabled=doc.get("avatar_enabled", True),
            rating_enabled=doc.get("rating_enabled", True),
            custom_questions=doc.get("custom_questions", []),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        ))

    return spaces_list


@router.get("/spaces/{space_id}", response_model=SpaceResponse)
async def get_single_space(
    space_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get details of a single Space owned by current user.
    Enforces IDOR authorization check.
    """
    obj_id = parse_object_id(space_id)
    spaces_coll = get_spaces_collection()

    space_doc = await spaces_coll.find_one({"_id": obj_id})
    if not space_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found."
        )

    # Authorization Check (IDOR)
    if str(space_doc["owner_id"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this Space."
        )

    return SpaceResponse(
        id=str(space_doc["_id"]),
        owner_id=str(space_doc["owner_id"]),
        name=space_doc["name"],
        slug=space_doc["slug"],
        custom_prompt=space_doc.get("custom_prompt"),
        logo_url=space_doc.get("logo_url"),
        avatar_enabled=space_doc.get("avatar_enabled", True),
        rating_enabled=space_doc.get("rating_enabled", True),
        custom_questions=space_doc.get("custom_questions", []),
        created_at=space_doc["created_at"],
        updated_at=space_doc["updated_at"]
    )


@router.put("/spaces/{space_id}", response_model=SpaceResponse)
async def update_space(
    space_id: str,
    req: SpaceUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update a Space owned by the current user.
    Enforces IDOR check and slug uniqueness.
    """
    obj_id = parse_object_id(space_id)
    spaces_coll = get_spaces_collection()

    space_doc = await spaces_coll.find_one({"_id": obj_id})
    if not space_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found."
        )

    # Authorization Check (IDOR)
    if str(space_doc["owner_id"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You cannot modify another user's Space."
        )

    update_data = {}

    # Check slug uniqueness if slug is being updated
    if req.slug is not None:
        new_slug = validate_and_normalize_slug(req.slug)
        if new_slug != space_doc["slug"]:
            slug_conflict = await spaces_coll.find_one({"slug": new_slug, "_id": {"$ne": obj_id}})
            if slug_conflict:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A Space with this slug already exists."
                )
            update_data["slug"] = new_slug

    if req.name is not None:
        update_data["name"] = req.name.strip()
    if req.custom_prompt is not None:
        update_data["custom_prompt"] = req.custom_prompt.strip() if req.custom_prompt else None
    if req.logo_url is not None:
        update_data["logo_url"] = req.logo_url
    if req.avatar_enabled is not None:
        update_data["avatar_enabled"] = req.avatar_enabled
    if req.rating_enabled is not None:
        update_data["rating_enabled"] = req.rating_enabled
    if req.custom_questions is not None:
        update_data["custom_questions"] = [q.model_dump() for q in req.custom_questions]

    now = datetime.now(timezone.utc)
    update_data["updated_at"] = now

    await spaces_coll.update_one({"_id": obj_id}, {"$set": update_data})

    updated_doc = await spaces_coll.find_one({"_id": obj_id})

    return SpaceResponse(
        id=str(updated_doc["_id"]),
        owner_id=str(updated_doc["owner_id"]),
        name=updated_doc["name"],
        slug=updated_doc["slug"],
        custom_prompt=updated_doc.get("custom_prompt"),
        logo_url=updated_doc.get("logo_url"),
        avatar_enabled=updated_doc.get("avatar_enabled", True),
        rating_enabled=updated_doc.get("rating_enabled", True),
        custom_questions=updated_doc.get("custom_questions", []),
        created_at=updated_doc["created_at"],
        updated_at=updated_doc["updated_at"]
    )


@router.delete("/spaces/{space_id}", response_model=MessageResponse)
async def delete_space(
    space_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a Space owned by current user and remove associated testimonials.
    Enforces IDOR check.
    """
    obj_id = parse_object_id(space_id)
    spaces_coll = get_spaces_collection()

    space_doc = await spaces_coll.find_one({"_id": obj_id})
    if not space_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found."
        )

    # Authorization Check (IDOR)
    if str(space_doc["owner_id"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You cannot delete another user's Space."
        )

    # Delete Space document
    await spaces_coll.delete_one({"_id": obj_id})

    # Delete related testimonials to avoid orphaned documents
    testimonials_coll = get_testimonials_collection()
    await testimonials_coll.delete_many({
        "$or": [
            {"space_id": space_id},
            {"space_id": obj_id}
        ]
    })

    return MessageResponse(message="Space and associated testimonials deleted successfully.")


@router.get("/public/spaces/{space_slug}", response_model=PublicSpaceResponse)
async def get_public_space_config(space_slug: str):
    """
    Public endpoint retrieving public configuration for a Space by slug.
    No authentication required. Returns only safe public fields.
    """
    slug_clean = validate_and_normalize_slug(space_slug)
    spaces_coll = get_spaces_collection()

    space_doc = await spaces_coll.find_one({"slug": slug_clean})
    if not space_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found."
        )

    return PublicSpaceResponse(
        name=space_doc["name"],
        slug=space_doc["slug"],
        custom_prompt=space_doc.get("custom_prompt"),
        logo_url=space_doc.get("logo_url"),
        avatar_enabled=space_doc.get("avatar_enabled", True),
        rating_enabled=space_doc.get("rating_enabled", True),
        custom_questions=space_doc.get("custom_questions", [])
    )
