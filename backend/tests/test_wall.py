from datetime import datetime, timezone, timedelta
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.testimonial import TestimonialStatus

client = TestClient(app)


class MockWallDB:
    def __init__(self):
        self.spaces = {}
        self.testimonials = {}

    def clear(self):
        self.spaces.clear()
        self.testimonials.clear()


test_db = MockWallDB()


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


# Helper to create a space in mock DB
def create_test_space(
    name="Test Space",
    slug="test-space",
    owner_id="secret_owner_id_999",
    custom_prompt="Please share your thoughts",
    logo_url="https://example.com/logo.png",
    avatar_enabled=True,
    rating_enabled=True
):
    sid = str(ObjectId())
    space_doc = {
        "_id": ObjectId(sid),
        "owner_id": owner_id,
        "name": name,
        "slug": slug,
        "custom_prompt": custom_prompt,
        "logo_url": logo_url,
        "avatar_enabled": avatar_enabled,
        "rating_enabled": rating_enabled,
        "custom_questions": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    test_db.spaces[sid] = space_doc
    return space_doc


# Helper to create a testimonial in mock DB
def create_test_testimonial(
    space_id,
    client_name="Rahul Sharma",
    client_email="rahul@example.com",
    company_role="Product Manager",
    rating=5,
    review_text="This platform transformed our feedback workflow!",
    avatar_url="https://example.com/avatar.jpg",
    status="approved",
    is_featured=False,
    created_at=None
):
    tid = str(ObjectId())
    now = created_at or datetime.now(timezone.utc)
    doc = {
        "_id": ObjectId(tid),
        "space_id": str(space_id),
        "client_name": client_name,
        "client_email": client_email,
        "company_role": company_role,
        "rating": rating,
        "review_text": review_text,
        "avatar_url": avatar_url,
        "status": status,
        "is_featured": is_featured,
        "custom_answers": [],
        "created_at": now,
        "updated_at": now
    }
    test_db.testimonials[tid] = doc
    return doc


# ─── 20 TEST CASES FOR MODULE 6 ──────────────────────────────────────────────

def test_01_public_wall_works_without_auth():
    """1. Public Wall of Love works without authentication."""
    space = create_test_space(slug="open-space")
    create_test_testimonial(space["_id"], status="approved")

    # Clear any cookies
    client.cookies.clear()
    res = client.get("/api/public/spaces/open-space/wall")
    assert res.status_code == 200
    data = res.json()
    assert "space" in data
    assert "testimonials" in data
    assert len(data["testimonials"]) == 1


def test_02_existing_space_slug_returns_correct_space():
    """2. Existing Space slug returns correct Space metadata."""
    create_test_space(name="Acme Corp", slug="acme-corp", custom_prompt="Tell us what you think!")

    res = client.get("/api/public/spaces/acme-corp/wall")
    assert res.status_code == 200
    data = res.json()
    assert data["space"]["name"] == "Acme Corp"
    assert data["space"]["slug"] == "acme-corp"
    assert data["space"]["custom_prompt"] == "Tell us what you think!"
    assert data["space"]["logo_url"] == "https://example.com/logo.png"


def test_03_invalid_space_slug_returns_404():
    """3. Invalid Space slug returns 404."""
    res = client.get("/api/public/spaces/non-existent-space-12345/wall")
    assert res.status_code == 404
    assert "Space not found" in res.json().get("detail", "")


def test_04_approved_testimonial_appears():
    """4. Approved testimonial appears on the Wall of Love."""
    space = create_test_space(slug="alpha-space")
    create_test_testimonial(space["_id"], client_name="Jane Doe", review_text="Loved the experience!", status="approved")

    res = client.get("/api/public/spaces/alpha-space/wall")
    assert res.status_code == 200
    items = res.json()["testimonials"]
    assert len(items) == 1
    assert items[0]["client_name"] == "Jane Doe"
    assert items[0]["review_text"] == "Loved the experience!"


def test_05_pending_testimonial_does_not_appear():
    """5. Pending testimonial does NOT appear on the Wall of Love."""
    space = create_test_space(slug="pending-test")
    create_test_testimonial(space["_id"], client_name="Pending Reviewer", status="pending")

    res = client.get("/api/public/spaces/pending-test/wall")
    assert res.status_code == 200
    assert len(res.json()["testimonials"]) == 0


def test_06_rejected_testimonial_does_not_appear():
    """6. Rejected testimonial does NOT appear on the Wall of Love."""
    space = create_test_space(slug="rejected-test")
    create_test_testimonial(space["_id"], client_name="Rejected Reviewer", status="rejected")

    res = client.get("/api/public/spaces/rejected-test/wall")
    assert res.status_code == 200
    assert len(res.json()["testimonials"]) == 0


def test_07_archived_testimonial_does_not_appear():
    """7. Archived testimonial does NOT appear on the Wall of Love."""
    space = create_test_space(slug="archived-test")
    create_test_testimonial(space["_id"], client_name="Archived Reviewer", status="archived")

    res = client.get("/api/public/spaces/archived-test/wall")
    assert res.status_code == 200
    assert len(res.json()["testimonials"]) == 0


def test_08_featured_approved_testimonial_appears_correctly():
    """8. Featured approved testimonial appears with is_featured=True."""
    space = create_test_space(slug="featured-space")
    create_test_testimonial(space["_id"], client_name="VIP Client", status="approved", is_featured=True)

    res = client.get("/api/public/spaces/featured-space/wall")
    assert res.status_code == 200
    items = res.json()["testimonials"]
    assert len(items) == 1
    assert items[0]["client_name"] == "VIP Client"
    assert items[0]["is_featured"] is True


def test_09_non_featured_approved_testimonial_appears():
    """9. Non-featured approved testimonial appears alongside featured testimonials."""
    space = create_test_space(slug="mixed-featured-space")
    create_test_testimonial(space["_id"], client_name="Regular Client", status="approved", is_featured=False)
    create_test_testimonial(space["_id"], client_name="Star Client", status="approved", is_featured=True)

    res = client.get("/api/public/spaces/mixed-featured-space/wall")
    assert res.status_code == 200
    items = res.json()["testimonials"]
    assert len(items) == 2
    names = [t["client_name"] for t in items]
    assert "Regular Client" in names
    assert "Star Client" in names


def test_10_space_a_testimonials_do_not_appear_on_space_b_wall():
    """10. Space A testimonials do not appear on Space B wall (strict isolation)."""
    space_a = create_test_space(name="Space Alpha", slug="space-alpha")
    space_b = create_test_space(name="Space Beta", slug="space-beta")

    create_test_testimonial(space_a["_id"], client_name="Alpha Client", status="approved")
    create_test_testimonial(space_b["_id"], client_name="Beta Client", status="approved")

    # Check Space A
    res_a = client.get("/api/public/spaces/space-alpha/wall")
    items_a = res_a.json()["testimonials"]
    assert len(items_a) == 1
    assert items_a[0]["client_name"] == "Alpha Client"

    # Check Space B
    res_b = client.get("/api/public/spaces/space-beta/wall")
    items_b = res_b.json()["testimonials"]
    assert len(items_b) == 1
    assert items_b[0]["client_name"] == "Beta Client"


def test_11_rating_setting_respected():
    """11. Rating setting is respected: if rating_enabled is False, rating is None."""
    # Space with rating disabled
    space_no_rating = create_test_space(slug="no-rating-space", rating_enabled=False)
    create_test_testimonial(space_no_rating["_id"], rating=5, status="approved")

    res = client.get("/api/public/spaces/no-rating-space/wall")
    assert res.status_code == 200
    data = res.json()
    assert data["space"]["rating_enabled"] is False
    assert data["testimonials"][0]["rating"] is None

    # Space with rating enabled
    space_with_rating = create_test_space(slug="with-rating-space", rating_enabled=True)
    create_test_testimonial(space_with_rating["_id"], rating=5, status="approved")

    res2 = client.get("/api/public/spaces/with-rating-space/wall")
    assert res2.status_code == 200
    assert res2.json()["space"]["rating_enabled"] is True
    assert res2.json()["testimonials"][0]["rating"] == 5


def test_12_avatar_setting_respected():
    """12. Avatar setting is respected: if avatar_enabled is False, avatar_url is None."""
    # Space with avatar disabled
    space_no_avatar = create_test_space(slug="no-avatar-space", avatar_enabled=False)
    create_test_testimonial(space_no_avatar["_id"], avatar_url="https://example.com/pic.jpg", status="approved")

    res = client.get("/api/public/spaces/no-avatar-space/wall")
    assert res.status_code == 200
    data = res.json()
    assert data["space"]["avatar_enabled"] is False
    assert data["testimonials"][0]["avatar_url"] is None

    # Space with avatar enabled
    space_with_avatar = create_test_space(slug="with-avatar-space", avatar_enabled=True)
    create_test_testimonial(space_with_avatar["_id"], avatar_url="https://example.com/pic.jpg", status="approved")

    res2 = client.get("/api/public/spaces/with-avatar-space/wall")
    assert res2.status_code == 200
    assert res2.json()["space"]["avatar_enabled"] is True
    assert res2.json()["testimonials"][0]["avatar_url"] == "https://example.com/pic.jpg"


def test_13_empty_state_works():
    """13. Empty state works: space exists but 0 approved testimonials."""
    create_test_space(name="Brand New Space", slug="brand-new")

    res = client.get("/api/public/spaces/brand-new/wall")
    assert res.status_code == 200
    data = res.json()
    assert data["space"]["name"] == "Brand New Space"
    assert data["testimonials"] == []


def test_14_missing_avatar_does_not_break_page():
    """14. Missing avatar in testimonial does not break API response."""
    space = create_test_space(slug="null-avatar-space", avatar_enabled=True)
    create_test_testimonial(space["_id"], avatar_url=None, status="approved")

    res = client.get("/api/public/spaces/null-avatar-space/wall")
    assert res.status_code == 200
    data = res.json()
    assert len(data["testimonials"]) == 1
    assert data["testimonials"][0]["avatar_url"] is None


def test_15_public_api_does_not_expose_client_email():
    """15. Public API does not expose client email."""
    space = create_test_space(slug="privacy-space")
    sensitive_email = "super_confidential_client@domain.org"
    create_test_testimonial(space["_id"], client_email=sensitive_email, status="approved")

    res = client.get("/api/public/spaces/privacy-space/wall")
    assert res.status_code == 200
    data = res.json()
    # Check dict structure
    assert "client_email" not in data["testimonials"][0]
    # Check raw text body
    assert sensitive_email not in res.text


def test_16_public_api_does_not_expose_owner_id():
    """16. Public API does not expose owner_id."""
    secret_owner = "owner_confidential_id_abc123"
    space = create_test_space(slug="owner-privacy-space", owner_id=secret_owner)
    create_test_testimonial(space["_id"], status="approved")

    res = client.get("/api/public/spaces/owner-privacy-space/wall")
    assert res.status_code == 200
    data = res.json()
    # Check space model
    assert "owner_id" not in data["space"]
    # Check testimonial model
    assert "owner_id" not in data["testimonials"][0]
    # Check raw text body
    assert secret_owner not in res.text


def test_17_html_route_serves_wall_html():
    """17. GET /wall/{space_slug} serves the HTML page without auth."""
    res = client.get("/wall/any-valid-slug")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Wall of Love" in res.text
    assert "masonry-grid" in res.text
    assert "wall-content" in res.text


def test_18_sorting_newest_first():
    """18. Testimonials are ordered newest first."""
    space = create_test_space(slug="sort-space")
    t1 = datetime.now(timezone.utc) - timedelta(days=5)
    t2 = datetime.now(timezone.utc) - timedelta(days=1)
    t3 = datetime.now(timezone.utc)

    create_test_testimonial(space["_id"], client_name="Oldest Review", created_at=t1, status="approved")
    create_test_testimonial(space["_id"], client_name="Middle Review", created_at=t2, status="approved")
    create_test_testimonial(space["_id"], client_name="Newest Review", created_at=t3, status="approved")

    res = client.get("/api/public/spaces/sort-space/wall")
    assert res.status_code == 200
    items = res.json()["testimonials"]
    assert len(items) == 3
    assert items[0]["client_name"] == "Newest Review"
    assert items[1]["client_name"] == "Middle Review"
    assert items[2]["client_name"] == "Oldest Review"


def test_19_slug_case_insensitivity_and_whitespace():
    """19. Space slug lookup is normalized for whitespace and case."""
    create_test_space(name="Case Space", slug="case-space")

    res_upper = client.get("/api/public/spaces/CASE-SPACE/wall")
    assert res_upper.status_code == 200
    assert res_upper.json()["space"]["slug"] == "case-space"

    res_spaces = client.get("/api/public/spaces/%20case-space%20/wall")
    assert res_spaces.status_code == 200
    assert res_spaces.json()["space"]["slug"] == "case-space"


def test_20_moderation_lifecycle_wall_visibility():
    """20. Testimonial visibility dynamically reflects moderation state transitions."""
    space = create_test_space(slug="lifecycle-space")
    doc = create_test_testimonial(space["_id"], client_name="Dynamic User", status="pending", is_featured=False)
    tid = str(doc["_id"])

    # 1. Pending: Not on wall
    res = client.get("/api/public/spaces/lifecycle-space/wall")
    assert len(res.json()["testimonials"]) == 0

    # 2. Approved: Visible on wall
    test_db.testimonials[tid]["status"] = TestimonialStatus.APPROVED.value
    res = client.get("/api/public/spaces/lifecycle-space/wall")
    assert len(res.json()["testimonials"]) == 1
    assert res.json()["testimonials"][0]["is_featured"] is False

    # 3. Featured: Visible with featured indicator
    test_db.testimonials[tid]["is_featured"] = True
    res = client.get("/api/public/spaces/lifecycle-space/wall")
    assert len(res.json()["testimonials"]) == 1
    assert res.json()["testimonials"][0]["is_featured"] is True

    # 4. Rejected: Excluded from wall
    test_db.testimonials[tid]["status"] = TestimonialStatus.REJECTED.value
    res = client.get("/api/public/spaces/lifecycle-space/wall")
    assert len(res.json()["testimonials"]) == 0

    # 5. Archived: Excluded from wall
    test_db.testimonials[tid]["status"] = TestimonialStatus.ARCHIVED.value
    res = client.get("/api/public/spaces/lifecycle-space/wall")
    assert len(res.json()["testimonials"]) == 0
