from datetime import datetime, timezone, timedelta
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.testimonial import TestimonialStatus

client = TestClient(app)


class MockEmbedDB:
    def __init__(self):
        self.spaces = {}
        self.testimonials = {}

    def clear(self):
        self.spaces.clear()
        self.testimonials.clear()


test_db = MockEmbedDB()


@pytest.fixture(autouse=True)
def setup_and_teardown():
    test_db.clear()
    yield
    test_db.clear()


@pytest.fixture(autouse=True)
def patch_mongo_collections(monkeypatch):
    class AsyncSpacesColl:
        async def find_one(self, query):
            if "_id" in query:
                sid = str(query["_id"])
                return test_db.spaces.get(sid)
            if "slug" in query:
                slug_val = query["slug"]
                for s in test_db.spaces.values():
                    if s["slug"] == slug_val:
                        return s
                return None
            return None

        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.spaces[doc_id] = doc
            class Res:
                inserted_id = doc["_id"]
            return Res()

    class AsyncTestimonialsColl:
        async def find_one(self, query):
            if "_id" in query:
                tid = str(query["_id"])
                return test_db.testimonials.get(tid)
            return None

        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.testimonials[doc_id] = doc
            class Res:
                inserted_id = doc["_id"]
            return Res()

        def find(self, query, *args, **kwargs):
            results = []
            for tdoc in test_db.testimonials.values():
                # Filter space_id
                if "space_id" in query:
                    sp_cond = query["space_id"]
                    if isinstance(sp_cond, dict) and "$in" in sp_cond:
                        allowed = [str(x) for x in sp_cond["$in"]]
                        if str(tdoc.get("space_id")) not in allowed:
                            continue
                    elif str(tdoc.get("space_id")) != str(sp_cond):
                        continue

                # Filter status
                if "status" in query:
                    if tdoc.get("status") != query["status"]:
                        continue

                results.append(dict(tdoc))

            class AsyncCursor:
                def __init__(self, data):
                    self.data = list(data)

                def sort(self, key, direction=1):
                    reverse = direction < 0
                    try:
                        self.data.sort(
                            key=lambda d: d.get(key) or datetime.min.replace(tzinfo=timezone.utc),
                            reverse=reverse
                        )
                    except Exception:
                        pass
                    return self

                def __aiter__(self):
                    self._iter = iter(self.data)
                    return self

                async def __anext__(self):
                    try:
                        return next(self._iter)
                    except StopIteration:
                        raise StopAsyncIteration

            return AsyncCursor(results)

    monkeypatch.setattr("backend.app.api.testimonials.get_spaces_collection", lambda: AsyncSpacesColl())
    monkeypatch.setattr("backend.app.api.testimonials.get_testimonials_collection", lambda: AsyncTestimonialsColl())


def create_space(name="Test Space", slug="test-space", avatar_enabled=True, rating_enabled=True):
    sid = str(ObjectId())
    doc = {
        "_id": ObjectId(sid),
        "owner_id": "owner_12345",
        "name": name,
        "slug": slug,
        "custom_prompt": "Tell us what you think!",
        "logo_url": "https://example.com/logo.png",
        "avatar_enabled": avatar_enabled,
        "rating_enabled": rating_enabled,
        "custom_questions": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    test_db.spaces[sid] = doc
    return doc


def create_testimonial(space_id, name="Jane Doe", rating=5, text="Awesome product!", status="approved", is_featured=False, created_at=None):
    tid = str(ObjectId())
    now = created_at or datetime.now(timezone.utc)
    doc = {
        "_id": ObjectId(tid),
        "space_id": str(space_id),
        "client_name": name,
        "client_email": f"{name.lower().replace(' ', '')}@example.com",
        "company_role": "Engineer",
        "rating": rating,
        "review_text": text,
        "avatar_url": "https://example.com/avatar.jpg",
        "status": status,
        "is_featured": is_featured,
        "custom_answers": [],
        "created_at": now,
        "updated_at": now,
    }
    test_db.testimonials[tid] = doc
    return doc


# ─── TEST CASES ───────────────────────────────────────────────────────────────

def test_01_public_embed_api_without_auth():
    """1. Public embed API works without any login or cookies."""
    sp = create_space(slug="public-embed-space")
    create_testimonial(sp["_id"], status="approved")

    client.cookies.clear()
    res = client.get("/api/public/spaces/public-embed-space/embed")
    assert res.status_code == 200
    data = res.json()
    assert data["space"]["slug"] == "public-embed-space"
    assert len(data["testimonials"]) == 1


def test_02_public_embed_html_page_without_auth():
    """2. Public /embed/{slug} webpage is served without login."""
    res = client.get("/embed/any-slug")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "embed-grid" in res.text
    assert "carousel-container" in res.text


def test_03_invalid_slug_returns_404():
    """3. Invalid space slug returns 404."""
    res = client.get("/api/public/spaces/invalid-slug-999/embed")
    assert res.status_code == 404
    assert "Space not found" in res.json().get("detail", "")


def test_04_default_embed_type_is_grid():
    """4. When type query param is omitted, default embed_type is 'grid'."""
    sp = create_space(slug="default-type-space")
    res = client.get("/api/public/spaces/default-type-space/embed")
    assert res.status_code == 200
    assert res.json()["embed_type"] == "grid"


def test_05_carousel_embed_type():
    """5. When ?type=carousel, response returns embed_type='carousel'."""
    sp = create_space(slug="carousel-type-space")
    res = client.get("/api/public/spaces/carousel-type-space/embed?type=carousel")
    assert res.status_code == 200
    assert res.json()["embed_type"] == "carousel"


def test_06_badge_embed_type_and_stats():
    """6. When ?type=badge, response returns embed_type='badge' with total_approved and average_rating."""
    sp = create_space(slug="badge-space")
    create_testimonial(sp["_id"], rating=5, status="approved")
    create_testimonial(sp["_id"], rating=4, status="approved")

    res = client.get("/api/public/spaces/badge-space/embed?type=badge")
    assert res.status_code == 200
    data = res.json()
    assert data["embed_type"] == "badge"
    assert data["total_approved"] == 2
    assert data["average_rating"] == 4.5


def test_07_badge_empty_state():
    """7. Badge on zero-review space returns total_approved=0 and average_rating=None."""
    sp = create_space(slug="empty-badge-space")
    res = client.get("/api/public/spaces/empty-badge-space/embed?type=badge")
    assert res.status_code == 200
    data = res.json()
    assert data["total_approved"] == 0
    assert data["average_rating"] is None


def test_08_pending_testimonials_excluded():
    """8. Pending testimonials must NEVER appear in embed."""
    sp = create_space(slug="pending-excl-space")
    create_testimonial(sp["_id"], name="Pending Person", status="pending")

    res = client.get("/api/public/spaces/pending-excl-space/embed")
    assert res.status_code == 200
    assert len(res.json()["testimonials"]) == 0
    assert res.json()["total_approved"] == 0


def test_09_rejected_testimonials_excluded():
    """9. Rejected testimonials must NEVER appear in embed."""
    sp = create_space(slug="rejected-excl-space")
    create_testimonial(sp["_id"], name="Spam Bot", status="rejected")

    res = client.get("/api/public/spaces/rejected-excl-space/embed")
    assert res.status_code == 200
    assert len(res.json()["testimonials"]) == 0


def test_10_archived_testimonials_excluded():
    """10. Archived testimonials must NEVER appear in embed."""
    sp = create_space(slug="archived-excl-space")
    create_testimonial(sp["_id"], name="Old Customer", status="archived")

    res = client.get("/api/public/spaces/archived-excl-space/embed")
    assert res.status_code == 200
    assert len(res.json()["testimonials"]) == 0


def test_11_featured_testimonials_reflected():
    """11. Featured approved testimonials have is_featured=True in embed response."""
    sp = create_space(slug="featured-embed-space")
    create_testimonial(sp["_id"], name="VIP Star", status="approved", is_featured=True)

    res = client.get("/api/public/spaces/featured-embed-space/embed")
    assert res.status_code == 200
    items = res.json()["testimonials"]
    assert len(items) == 1
    assert items[0]["is_featured"] is True


def test_12_space_isolation_in_embed():
    """12. Space A testimonials do not leak into Space B embed."""
    sp_a = create_space(slug="space-a-embed")
    sp_b = create_space(slug="space-b-embed")

    create_testimonial(sp_a["_id"], name="Alpha Customer", status="approved")
    create_testimonial(sp_b["_id"], name="Beta Customer", status="approved")

    res_a = client.get("/api/public/spaces/space-a-embed/embed")
    names_a = [t["client_name"] for t in res_a.json()["testimonials"]]
    assert "Alpha Customer" in names_a
    assert "Beta Customer" not in names_a

    res_b = client.get("/api/public/spaces/space-b-embed/embed")
    names_b = [t["client_name"] for t in res_b.json()["testimonials"]]
    assert "Beta Customer" in names_b
    assert "Alpha Customer" not in names_b


def test_13_rating_disabled_masks_rating():
    """13. If space has rating_enabled=False, rating is masked to None."""
    sp = create_space(slug="no-rating-embed", rating_enabled=False)
    create_testimonial(sp["_id"], rating=5, status="approved")

    res = client.get("/api/public/spaces/no-rating-embed/embed")
    assert res.status_code == 200
    data = res.json()
    assert data["space"]["rating_enabled"] is False
    assert data["testimonials"][0]["rating"] is None


def test_14_avatar_disabled_masks_avatar():
    """14. If space has avatar_enabled=False, avatar_url is masked to None."""
    sp = create_space(slug="no-avatar-embed", avatar_enabled=False)
    create_testimonial(sp["_id"], status="approved")

    res = client.get("/api/public/spaces/no-avatar-embed/embed")
    assert res.status_code == 200
    data = res.json()
    assert data["space"]["avatar_enabled"] is False
    assert data["testimonials"][0]["avatar_url"] is None


def test_15_privacy_client_email_never_exposed():
    """15. Public embed API never exposes customer email address."""
    sp = create_space(slug="privacy-embed-space")
    create_testimonial(sp["_id"], name="Secret User", status="approved")

    res = client.get("/api/public/spaces/privacy-embed-space/embed")
    assert res.status_code == 200
    assert "client_email" not in res.json()["testimonials"][0]
    assert "secretuser@example.com" not in res.text


def test_16_privacy_owner_id_never_exposed():
    """16. Public embed API never exposes owner_id."""
    sp = create_space(slug="owner-privacy-embed")
    create_testimonial(sp["_id"], status="approved")

    res = client.get("/api/public/spaces/owner-privacy-embed/embed")
    assert res.status_code == 200
    assert "owner_id" not in res.json()["space"]
    assert "owner_id" not in res.json()["testimonials"][0]
    assert "owner_12345" not in res.text


def test_17_sorting_newest_first():
    """17. Testimonials in embed are ordered newest first."""
    sp = create_space(slug="sort-embed-space")
    t_old = datetime.now(timezone.utc) - timedelta(days=5)
    t_new = datetime.now(timezone.utc)

    create_testimonial(sp["_id"], name="Older", created_at=t_old, status="approved")
    create_testimonial(sp["_id"], name="Newer", created_at=t_new, status="approved")

    res = client.get("/api/public/spaces/sort-embed-space/embed")
    items = res.json()["testimonials"]
    assert items[0]["client_name"] == "Newer"
    assert items[1]["client_name"] == "Older"


def test_18_slug_normalization_case_and_whitespace():
    """18. Space slug lookup normalizes case and whitespace."""
    create_space(slug="case-embed-space")
    res = client.get("/api/public/spaces/CASE-EMBED-SPACE/embed")
    assert res.status_code == 200
    assert res.json()["space"]["slug"] == "case-embed-space"

    res2 = client.get("/api/public/spaces/%20case-embed-space%20/embed")
    assert res2.status_code == 200


def test_19_invalid_embed_type_falls_back_to_grid():
    """19. Unsupported embed type query parameter defaults safely to 'grid'."""
    sp = create_space(slug="fallback-type-space")
    res = client.get("/api/public/spaces/fallback-type-space/embed?type=unsupported_type")
    assert res.status_code == 200
    assert res.json()["embed_type"] == "grid"


def test_20_mixed_moderation_lifecycle_embed_visibility():
    """20. Testimonial appears only after approval, and disappears on rejection."""
    sp = create_space(slug="lifecycle-embed-space")
    doc = create_testimonial(sp["_id"], name="Dynamic Customer", status="pending")
    tid = str(doc["_id"])

    # 1. Pending: Not in embed
    res1 = client.get("/api/public/spaces/lifecycle-embed-space/embed")
    assert len(res1.json()["testimonials"]) == 0

    # 2. Approved: Visible in embed
    test_db.testimonials[tid]["status"] = TestimonialStatus.APPROVED.value
    res2 = client.get("/api/public/spaces/lifecycle-embed-space/embed")
    assert len(res2.json()["testimonials"]) == 1

    # 3. Rejected: Removed from embed
    test_db.testimonials[tid]["status"] = TestimonialStatus.REJECTED.value
    res3 = client.get("/api/public/spaces/lifecycle-embed-space/embed")
    assert len(res3.json()["testimonials"]) == 0
