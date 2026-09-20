"""
MODULE 7 — Rating Analytics & Statistics
Authenticated analytics endpoint for Space owners.
GET /api/analytics/overview
"""
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.auth_dependency import get_current_user
from backend.app.db.mongodb import get_spaces_collection, get_testimonials_collection
from backend.app.schemas.testimonial import (
    AnalyticsResponse,
    StarDistribution,
    StatusDistribution,
)

router = APIRouter(tags=["Analytics"])


async def _collect_space_ids_for_owner(owner_id_str: str) -> list[str]:
    """Return list of space_id strings that belong to the authenticated owner."""
    spaces_coll = get_spaces_collection()
    space_ids: list[str] = []
    async for doc in spaces_coll.find({"owner_id": owner_id_str}):
        space_ids.append(str(doc["_id"]))
    return space_ids


async def _compute_analytics(space_ids: list[str]) -> dict:
    """
    Compute analytics counters from MongoDB for the given list of space_ids.
    Returns raw tallies used to build AnalyticsResponse.
    """
    testimonials_coll = get_testimonials_collection()

    # Build space_id filter accepting both string and ObjectId forms
    id_filter_list: list = []
    for sid in space_ids:
        id_filter_list.append(sid)
        try:
            id_filter_list.append(ObjectId(sid))
        except Exception:
            pass

    query = {"space_id": {"$in": id_filter_list}} if id_filter_list else {"space_id": "__no_match__"}

    # Counters
    total_reviews = 0
    featured_reviews = 0
    status_counts = {"pending": 0, "approved": 0, "rejected": 0, "archived": 0}
    star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    rating_sum = 0
    rating_count = 0

    async for doc in testimonials_coll.find(query):
        total_reviews += 1

        # Status distribution
        s = doc.get("status", "pending")
        if s in status_counts:
            status_counts[s] += 1

        # Featured
        if doc.get("is_featured", False):
            featured_reviews += 1

        # Star distribution & average
        r = doc.get("rating")
        if r and isinstance(r, int) and 1 <= r <= 5:
            star_counts[r] += 1
            rating_sum += r
            rating_count += 1

    average_rating: Optional[float] = None
    if rating_count > 0:
        average_rating = round(rating_sum / rating_count, 1)

    return {
        "total_reviews": total_reviews,
        "featured_reviews": featured_reviews,
        "status_counts": status_counts,
        "star_counts": star_counts,
        "average_rating": average_rating,
    }


@router.get(
    "/api/analytics/overview",
    response_model=AnalyticsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_analytics_overview(
    current_user: dict = Depends(get_current_user),
    space_id: Optional[str] = Query(
        None,
        description="Optional Space ID to scope analytics. Omit for all owned Spaces."
    ),
):
    """
    Return aggregated analytics for the authenticated owner.

    - If space_id is provided: statistics for that Space only (ownership verified).
    - If no space_id: combined statistics across all Spaces owned by this owner.

    Security:
    - Owner is determined from authenticated JWT — never from the request body.
    - Cross-owner access is denied with HTTP 403.
    """
    owner_id_str = current_user["id"]
    spaces_coll = get_spaces_collection()

    if space_id:
        # Validate ownership of the requested space
        target_space = None
        try:
            target_space = await spaces_coll.find_one({"_id": ObjectId(space_id)})
        except Exception:
            pass
        if not target_space:
            target_space = await spaces_coll.find_one({"_id": space_id})
        if not target_space:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Space not found."
            )
        if str(target_space.get("owner_id")) != str(owner_id_str):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view analytics for this Space."
            )

        scoped_space_ids = [str(target_space["_id"])]
        space_name = target_space.get("name")
        scope = str(target_space["_id"])
        total_spaces = 1
    else:
        # All spaces owned by this user
        scoped_space_ids = await _collect_space_ids_for_owner(owner_id_str)
        space_name = None
        scope = "all"
        total_spaces = len(scoped_space_ids)

    data = await _compute_analytics(scoped_space_ids)

    return AnalyticsResponse(
        scope=scope,
        space_name=space_name,
        total_reviews=data["total_reviews"],
        featured_reviews=data["featured_reviews"],
        total_spaces=total_spaces,
        average_rating=data["average_rating"],
        star_distribution=StarDistribution(
            star_1=data["star_counts"][1],
            star_2=data["star_counts"][2],
            star_3=data["star_counts"][3],
            star_4=data["star_counts"][4],
            star_5=data["star_counts"][5],
        ),
        status_distribution=StatusDistribution(
            pending=data["status_counts"]["pending"],
            approved=data["status_counts"]["approved"],
            rejected=data["status_counts"]["rejected"],
            archived=data["status_counts"]["archived"],
        ),
    )
