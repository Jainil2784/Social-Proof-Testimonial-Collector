from datetime import datetime, timezone
import math
import re
from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.auth_dependency import get_current_user
from backend.app.db.mongodb import get_spaces_collection, get_testimonials_collection
from backend.app.models.testimonial import TestimonialStatus
from backend.app.schemas.testimonial import (
    TestimonialFeaturedUpdateRequest,
    TestimonialModerationResponse,
    TestimonialPaginationResponse,
    TestimonialStatsResponse,
    TestimonialStatusUpdateRequest,
)

router = APIRouter(tags=["Review Moderation"])


def parse_object_id(id_str: str) -> ObjectId:
    """Helper to convert string to ObjectId or raise 400 Bad Request."""
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Testimonial ID format."
        )


async def get_testimonial_and_verify_owner(testimonial_id: str, owner_id: str):
    """
    IDOR Protection:
    1. Authenticate current user.
    2. Find testimonial.
    3. Find associated Space.
    4. Verify Space.owner_id == current authenticated user ID.
    5. If ownership fails or space does not exist: raise 403 Forbidden.
    """
    obj_id = parse_object_id(testimonial_id)
    testimonials_coll = get_testimonials_collection()
    spaces_coll = get_spaces_collection()

    testimonial = await testimonials_coll.find_one({"_id": obj_id})
    if not testimonial:
        testimonial = await testimonials_coll.find_one({"_id": str(obj_id)})
    if not testimonial:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Testimonial not found."
        )

    space_id_val = testimonial.get("space_id")
    space = None
    try:
        space = await spaces_coll.find_one({"_id": ObjectId(str(space_id_val))})
    except Exception:
        pass
    if not space:
        space = await spaces_coll.find_one({"_id": str(space_id_val)})

    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated Space not found."
        )

    if str(space.get("owner_id")) != str(owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own the Space associated with this testimonial."
        )

    return testimonial, space


def build_testimonial_response(doc: dict, space_info: dict) -> TestimonialModerationResponse:
    """Constructs a clean, timezone-aware TestimonialModerationResponse."""
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")

    if isinstance(created_at, datetime) and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elif not isinstance(created_at, datetime):
        created_at = datetime.now(timezone.utc)

    if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    elif not isinstance(updated_at, datetime):
        updated_at = datetime.now(timezone.utc)

    return TestimonialModerationResponse(
        id=str(doc["_id"]),
        space_id=str(doc.get("space_id", "")),
        space_name=space_info.get("name", "Unknown Space"),
        space_slug=space_info.get("slug", ""),
        client_name=doc.get("client_name", ""),
        client_email=doc.get("client_email", ""),
        company_role=doc.get("company_role"),
        rating=doc.get("rating"),
        review_text=doc.get("review_text", ""),
        avatar_url=doc.get("avatar_url"),
        custom_answers=doc.get("custom_answers", []),
        status=doc.get("status", "pending"),
        is_featured=doc.get("is_featured", False),
        created_at=created_at,
        updated_at=updated_at,
    )


# ─── MODERATION STATS ────────────────────────────────────────────────────────
@router.get("/api/testimonials/stats", response_model=TestimonialStatsResponse)
@router.get("/api/owner/stats")
async def get_testimonials_stats(current_user: dict = Depends(get_current_user)):
    """
    Return aggregated statistics for the owner dashboard and moderation view.
    Derived strictly from real MongoDB data for the authenticated owner's Spaces.
    """
    spaces_coll = get_spaces_collection()
    testimonials_coll = get_testimonials_collection()
    owner_id_str = current_user["id"]

    space_ids = []
    async for doc in spaces_coll.find({"owner_id": owner_id_str}, {"_id": 1}):
        space_ids.append(str(doc["_id"]))

    total_spaces = len(space_ids)
    total_reviews = 0
    pending = 0
    approved = 0
    rejected = 0
    archived = 0
    featured = 0

    if space_ids:
        space_id_filters = []
        for sid in space_ids:
            space_id_filters.append(sid)
            try:
                space_id_filters.append(ObjectId(sid))
            except Exception:
                pass

        async for doc in testimonials_coll.find({"space_id": {"$in": space_id_filters}}):
            s = doc.get("status", "pending")
            total_reviews += 1
            if s == "pending":
                pending += 1
            elif s == "approved":
                approved += 1
            elif s == "rejected":
                rejected += 1
            elif s == "archived":
                archived += 1

            if doc.get("is_featured", False):
                featured += 1

    return {
        "total_spaces": total_spaces,
        "total_reviews": total_reviews,
        "pending_reviews": pending,
        "approved_reviews": approved,
        "rejected_reviews": rejected,
        "archived_reviews": archived,
        "featured_reviews": featured,
    }


# ─── GET PAGINATED TESTIMONIALS WITH FILTERS ────────────────────────────────
@router.get("/api/testimonials", response_model=TestimonialPaginationResponse)
async def list_testimonials_paginated(
    current_user: dict = Depends(get_current_user),
    space_id: Optional[str] = Query(None, description="Filter by Space ID"),
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, archived"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filter by star rating (1-5)"),
    search: Optional[str] = Query(None, description="Search across customer name, email, role, or review text"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
):
    """
    List testimonials belonging ONLY to Spaces owned by the authenticated user.
    Supports filtering by space_id, status, rating, keyword search, and pagination.
    """
    spaces_coll = get_spaces_collection()
    testimonials_coll = get_testimonials_collection()
    owner_id_str = current_user["id"]

    # Step 1: Collect owned spaces
    owner_spaces = {}
    async for space_doc in spaces_coll.find({"owner_id": owner_id_str}):
        sid = str(space_doc["_id"])
        owner_spaces[sid] = {
            "name": space_doc.get("name", "Unknown Space"),
            "slug": space_doc.get("slug", ""),
        }

    if not owner_spaces:
        return TestimonialPaginationResponse(
            items=[],
            page=page,
            limit=limit,
            total=0,
            pages=0,
        )

    # Step 2: Build scoped space_id filter
    if space_id:
        if space_id not in owner_spaces:
            # Owner does not own this space
            return TestimonialPaginationResponse(
                items=[],
                page=page,
                limit=limit,
                total=0,
                pages=0,
            )
        target_spaces = [space_id]
    else:
        target_spaces = list(owner_spaces.keys())

    space_id_filters = []
    for sid in target_spaces:
        space_id_filters.append(sid)
        try:
            space_id_filters.append(ObjectId(sid))
        except Exception:
            pass

    query: dict = {"space_id": {"$in": space_id_filters}}

    # Status filter
    if status:
        status_clean = status.lower().strip()
        allowed = {s.value for s in TestimonialStatus}
        if status_clean in allowed:
            query["status"] = status_clean
        else:
            return TestimonialPaginationResponse(
                items=[],
                page=page,
                limit=limit,
                total=0,
                pages=0,
            )

    # Rating filter
    if rating is not None:
        query["rating"] = rating

    # Keyword Search filter (safe regex)
    if search and search.strip():
        safe_kw = re.escape(search.strip())
        query["$or"] = [
            {"client_name": {"$regex": safe_kw, "$options": "i"}},
            {"client_email": {"$regex": safe_kw, "$options": "i"}},
            {"company_role": {"$regex": safe_kw, "$options": "i"}},
            {"review_text": {"$regex": safe_kw, "$options": "i"}},
        ]

    # Step 3: Count total matching documents
    total = await testimonials_coll.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0

    # Step 4: Fetch paginated items sorted by created_at DESC
    skip = (page - 1) * limit
    cursor = testimonials_coll.find(query).sort("created_at", -1).skip(skip).limit(limit)

    items = []
    async for doc in cursor:
        sid = str(doc.get("space_id", ""))
        space_info = owner_spaces.get(sid, {"name": "Unknown Space", "slug": ""})
        items.append(build_testimonial_response(doc, space_info))

    return TestimonialPaginationResponse(
        items=items,
        page=page,
        limit=limit,
        total=total,
        pages=pages,
    )


# ─── COMPATIBILITY ENDPOINT FOR EXISTING CALLS ──────────────────────────────
@router.get("/api/owner/testimonials", response_model=List[TestimonialModerationResponse])
async def list_owner_testimonials_compat(
    current_user: dict = Depends(get_current_user),
    status: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    rating: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
):
    """Compatibility list endpoint for dashboard home and previous modules."""
    res = await list_testimonials_paginated(
        current_user=current_user,
        space_id=space_id,
        status=status,
        rating=rating,
        search=search,
        page=1,
        limit=limit,
    )
    return res.items


# ─── GET SINGLE TESTIMONIAL ─────────────────────────────────────────────────
@router.get("/api/testimonials/{testimonial_id}", response_model=TestimonialModerationResponse)
async def get_single_testimonial(
    testimonial_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get a single testimonial with IDOR security verification.
    """
    testimonial, space = await get_testimonial_and_verify_owner(testimonial_id, current_user["id"])
    return build_testimonial_response(testimonial, space)


# ─── APPROVE / REJECT / ARCHIVE (STATUS UPDATE) ─────────────────────────────
@router.patch("/api/testimonials/{testimonial_id}/status", response_model=TestimonialModerationResponse)
async def update_testimonial_status(
    testimonial_id: str,
    req: TestimonialStatusUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Update testimonial moderation status (pending, approved, rejected, archived).
    Enforces IDOR verification. Updates updated_at timestamp.
    """
    try:
        status_clean = req.get_normalized_status()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    testimonial, space = await get_testimonial_and_verify_owner(testimonial_id, current_user["id"])

    now = datetime.now(timezone.utc)
    testimonials_coll = get_testimonials_collection()

    await testimonials_coll.update_one(
        {"_id": testimonial["_id"]},
        {"$set": {"status": status_clean, "updated_at": now}}
    )

    testimonial["status"] = status_clean
    testimonial["updated_at"] = now

    return build_testimonial_response(testimonial, space)


# ─── FEATURE / UNFEATURE ────────────────────────────────────────────────────
@router.patch("/api/testimonials/{testimonial_id}/featured", response_model=TestimonialModerationResponse)
async def update_testimonial_featured(
    testimonial_id: str,
    req: TestimonialFeaturedUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Toggle or set is_featured state for approved or pending testimonials.
    Enforces IDOR verification. Updates updated_at timestamp.
    """
    testimonial, space = await get_testimonial_and_verify_owner(testimonial_id, current_user["id"])

    now = datetime.now(timezone.utc)
    testimonials_coll = get_testimonials_collection()

    await testimonials_coll.update_one(
        {"_id": testimonial["_id"]},
        {"$set": {"is_featured": req.is_featured, "updated_at": now}}
    )

    testimonial["is_featured"] = req.is_featured
    testimonial["updated_at"] = now

    return build_testimonial_response(testimonial, space)
