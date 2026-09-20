"""
MODULE 7 — Analytics Test Suite
24 test cases covering security, accuracy, and all distribution calculations.
"""
from datetime import datetime, timezone
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


# ─── In-memory Mock DB ────────────────────────────────────────────────────────
class MockAnalyticsDB:
    def __init__(self):
        self.users = {}
        self.email_verification_tokens = {}
        self.auth_sessions = {}
        self.password_reset_tokens = {}
        self.spaces = {}
        self.testimonials = {}

    def clear(self):
        for d in (self.users, self.email_verification_tokens, self.auth_sessions,
                  self.password_reset_tokens, self.spaces, self.testimonials):
            d.clear()


test_db = MockAnalyticsDB()


@pytest.fixture(autouse=True)
def setup_and_teardown():
    test_db.clear()
    yield
    test_db.clear()


@pytest.fixture(autouse=True)
def patch_mongo_collections(monkeypatch):
    class AsyncUsersColl:
        async def find_one(self, query):
            if "_id" in query:
                return test_db.users.get(str(query["_id"]))
            if "email" in query:
                for u in test_db.users.values():
                    if u["email"] == query["email"]:
                        return u
            return None

        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.users[doc_id] = doc
            class R:
                inserted_id = doc["_id"]
            return R()

        async def update_one(self, q, u):
            for doc in test_db.users.values():
                if "_id" in q and str(doc.get("_id")) == str(q["_id"]):
                    if "$set" in u:
                        doc.update(u["$set"])

    class AsyncSessionsColl:
        async def find_one(self, query):
            if "token_id" in query:
                return test_db.auth_sessions.get(query["token_id"])
            return None

        async def insert_one(self, doc):
            doc["_id"] = str(ObjectId())
            test_db.auth_sessions[doc["token_id"]] = doc

        async def update_one(self, q, u):
            for doc in test_db.auth_sessions.values():
                if str(doc.get("_id")) == str(q.get("_id")):
                    if "$set" in u:
                        doc.update(u["$set"])

    class AsyncVerifyColl:
        async def find_one(self, q):
            if "token" in q:
                return test_db.email_verification_tokens.get(q["token"])
            return None

        async def insert_one(self, doc):
            doc["_id"] = str(ObjectId())
            test_db.email_verification_tokens[doc["token"]] = doc

        async def update_one(self, q, u):
            pass

    class AsyncResetColl:
        async def find_one(self, q):
            if "token" in q:
                return test_db.password_reset_tokens.get(q["token"])
            return None

        async def insert_one(self, doc):
            doc["_id"] = str(ObjectId())
            test_db.password_reset_tokens[doc["token"]] = doc

        async def update_one(self, q, u):
            pass

    class AsyncSpacesColl:
        async def find_one(self, query):
            if "_id" in query:
                sid = str(query["_id"])
                return test_db.spaces.get(sid)
            if "slug" in query:
                for s in test_db.spaces.values():
                    if s["slug"] == query["slug"]:
                        return s
            return None

        def find(self, query, *args, **kwargs):
            results = []
            owner_id = query.get("owner_id")
            for doc in test_db.spaces.values():
                if owner_id is None or str(doc.get("owner_id")) == str(owner_id):
                    results.append(dict(doc))

            class Cursor:
                def __init__(self, data):
                    self.data = data
                def __aiter__(self):
                    self._iter = iter(self.data)
                    return self
                async def __anext__(self):
                    try:
                        return next(self._iter)
                    except StopIteration:
                        raise StopAsyncIteration
            return Cursor(results)

        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.spaces[doc_id] = doc
            class R:
                inserted_id = doc["_id"]
            return R()

        async def count_documents(self, query, *args, **kwargs):
            count = 0
            owner_id = query.get("owner_id")
            for doc in test_db.spaces.values():
                if owner_id is None or str(doc.get("owner_id")) == str(owner_id):
                    count += 1
            return count

    class AsyncTestimonialsColl:
        async def find_one(self, query, *args, **kwargs):
            if "_id" in query:
                return test_db.testimonials.get(str(query["_id"]))
            return None

        def find(self, query, *args, **kwargs):
            results = []
            for doc in test_db.testimonials.values():
                # space_id filter
                if "space_id" in query:
                    sp_cond = query["space_id"]
                    if isinstance(sp_cond, dict) and "$in" in sp_cond:
                        allowed = [str(x) for x in sp_cond["$in"]]
                        if str(doc.get("space_id")) not in allowed:
                            continue
                    elif str(doc.get("space_id")) != str(sp_cond):
                        continue
                # status filter
                if "status" in query:
                    if doc.get("status") != query["status"]:
                        continue
                results.append(dict(doc))

            class Cursor:
                def __init__(self, data):
                    self.data = data
                def sort(self, *a, **kw):
                    return self
                def skip(self, n):
                    self.data = self.data[n:]
                    return self
                def limit(self, n):
                    self.data = self.data[:n]
                    return self
                def __aiter__(self):
                    self._iter = iter(self.data)
                    return self
                async def __anext__(self):
                    try:
                        return next(self._iter)
                    except StopIteration:
                        raise StopAsyncIteration
            return Cursor(results)

        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.testimonials[doc_id] = doc
            class R:
                inserted_id = doc["_id"]
            return R()

        async def update_one(self, query, update, *args, **kwargs):
            for doc in test_db.testimonials.values():
                matched = True
                for k, v in query.items():
                    if k == "_id":
                        if str(doc.get("_id")) != str(v):
                            matched = False
                    elif doc.get(k) != v:
                        matched = False
                if matched:
                    if "$set" in update:
                        doc.update(update["$set"])
                    break

        async def count_documents(self, query, *args, **kwargs):
            count = 0
            for doc in test_db.testimonials.values():
                if "space_id" in query:
                    sp_cond = query["space_id"]
                    if isinstance(sp_cond, dict) and "$in" in sp_cond:
                        allowed = [str(x) for x in sp_cond["$in"]]
                        if str(doc.get("space_id")) not in allowed:
                            continue
                    elif str(doc.get("space_id")) != str(sp_cond):
                        continue
                if "status" in query:
                    if doc.get("status") != query["status"]:
                        continue
                count += 1
            return count

    monkeypatch.setattr("backend.app.api.analytics.get_spaces_collection", lambda: AsyncSpacesColl())
    monkeypatch.setattr("backend.app.api.analytics.get_testimonials_collection", lambda: AsyncTestimonialsColl())
    monkeypatch.setattr("backend.app.api.auth.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.api.auth.get_auth_sessions_collection", lambda: AsyncSessionsColl())
    monkeypatch.setattr("backend.app.api.auth.get_verification_tokens_collection", lambda: AsyncVerifyColl())
    monkeypatch.setattr("backend.app.core.auth_dependency.get_users_collection", lambda: AsyncUsersColl())


# ─── Helper factories ─────────────────────────────────────────────────────────
def _make_space(owner_id, name="Test Space", slug=None):
    sid = str(ObjectId())
    doc = {
        "_id": ObjectId(sid),
        "owner_id": str(owner_id),
        "name": name,
        "slug": slug or f"space-{sid[:8]}",
        "custom_prompt": None,
        "logo_url": None,
        "avatar_enabled": True,
        "rating_enabled": True,
        "custom_questions": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    test_db.spaces[sid] = doc
    return doc


def _make_testimonial(space_id, status="approved", rating=5, is_featured=False):
    tid = str(ObjectId())
    doc = {
        "_id": ObjectId(tid),
        "space_id": str(space_id),
        "client_name": "Test Customer",
        "client_email": f"customer_{tid[:6]}@test.com",
        "company_role": "Tester",
        "rating": rating,
        "review_text": "Great product!",
        "avatar_url": None,
        "status": status,
        "is_featured": is_featured,
        "custom_answers": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    test_db.testimonials[tid] = doc
    return doc


def _register_and_login(email="owner@test.io", password="Password123!", name="Test Owner"):
    client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    owner_id = None
    for u in test_db.users.values():
        if u["email"] == email:
            owner_id = str(u["_id"])
            break
    return owner_id


# ─── TESTS ────────────────────────────────────────────────────────────────────

def test_01_authenticated_owner_can_access_analytics():
    """1. Authenticated owner can access analytics."""
    _register_and_login()
    res = client.get("/api/analytics/overview", headers={})
    assert res.status_code == 200
    data = res.json()
    assert "total_reviews" in data
    assert "average_rating" in data


def test_02_unauthenticated_user_cannot_access_analytics():
    """2. Unauthenticated user gets 401."""
    client.cookies.clear()
    res = client.get("/api/analytics/overview")
    assert res.status_code == 401


def test_03_owner_sees_only_own_data():
    """3. Owner sees only statistics for their own Spaces."""
    owner_a_id = _register_and_login("owner_a@test.io", name="Owner A")
    space_a = _make_space(owner_a_id, name="Space A")
    _make_testimonial(space_a["_id"], status="approved", rating=5)
    _make_testimonial(space_a["_id"], status="pending", rating=4)

    # Another owner's space with testimonials (should NOT appear)
    owner_b_id = str(ObjectId())
    space_b = _make_space(owner_b_id, name="Space B")
    _make_testimonial(space_b["_id"], status="approved", rating=1)
    _make_testimonial(space_b["_id"], status="approved", rating=1)

    res = client.get("/api/analytics/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["total_reviews"] == 2  # Only owner A's 2 reviews


def test_04_owner_a_cannot_access_owner_b_space_stats():
    """4. Owner A gets 403 when requesting Owner B's Space analytics."""
    owner_a_id = _register_and_login("ownerx@test.io", name="Owner X")
    owner_b_id = str(ObjectId())
    space_b = _make_space(owner_b_id, name="Other's Space")
    space_b_id = str(space_b["_id"])

    res = client.get(f"/api/analytics/overview?space_id={space_b_id}")
    assert res.status_code == 403


def test_05_total_review_count_is_correct():
    """5. Total review count matches inserted testimonials."""
    owner_id = _register_and_login("t5@test.io", name="Owner T5")
    space = _make_space(owner_id)
    for i in range(7):
        _make_testimonial(space["_id"], status="approved", rating=(i % 5) + 1)

    res = client.get("/api/analytics/overview")
    assert res.status_code == 200
    assert res.json()["total_reviews"] == 7


def test_06_average_rating_is_correct():
    """6. Average rating is computed correctly from real data."""
    owner_id = _register_and_login("t6@test.io", name="Owner T6")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], rating=5)
    _make_testimonial(space["_id"], rating=3)
    _make_testimonial(space["_id"], rating=4)
    # Average: (5+3+4)/3 = 4.0

    res = client.get("/api/analytics/overview")
    assert res.status_code == 200
    assert res.json()["average_rating"] == 4.0


def test_07_five_star_count_is_correct():
    """7. 5-star count is correct."""
    owner_id = _register_and_login("t7@test.io", name="Owner T7")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], rating=5)
    _make_testimonial(space["_id"], rating=5)
    _make_testimonial(space["_id"], rating=4)

    data = client.get("/api/analytics/overview").json()
    assert data["star_distribution"]["star_5"] == 2


def test_08_four_star_count_is_correct():
    """8. 4-star count is correct."""
    owner_id = _register_and_login("t8@test.io", name="Owner T8")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], rating=4)
    _make_testimonial(space["_id"], rating=4)
    _make_testimonial(space["_id"], rating=5)

    data = client.get("/api/analytics/overview").json()
    assert data["star_distribution"]["star_4"] == 2


def test_09_three_star_count_is_correct():
    """9. 3-star count is correct."""
    owner_id = _register_and_login("t9@test.io", name="Owner T9")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], rating=3)
    _make_testimonial(space["_id"], rating=3)
    _make_testimonial(space["_id"], rating=3)

    data = client.get("/api/analytics/overview").json()
    assert data["star_distribution"]["star_3"] == 3


def test_10_two_star_count_is_correct():
    """10. 2-star count is correct."""
    owner_id = _register_and_login("t10@test.io", name="Owner T10")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], rating=2)
    _make_testimonial(space["_id"], rating=5)

    data = client.get("/api/analytics/overview").json()
    assert data["star_distribution"]["star_2"] == 1


def test_11_one_star_count_is_correct():
    """11. 1-star count is correct."""
    owner_id = _register_and_login("t11@test.io", name="Owner T11")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], rating=1)
    _make_testimonial(space["_id"], rating=5)
    _make_testimonial(space["_id"], rating=5)

    data = client.get("/api/analytics/overview").json()
    assert data["star_distribution"]["star_1"] == 1


def test_12_pending_count_is_correct():
    """12. Pending status count is correct."""
    owner_id = _register_and_login("t12@test.io", name="Owner T12")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], status="pending")
    _make_testimonial(space["_id"], status="pending")
    _make_testimonial(space["_id"], status="approved")

    data = client.get("/api/analytics/overview").json()
    assert data["status_distribution"]["pending"] == 2


def test_13_approved_count_is_correct():
    """13. Approved status count is correct."""
    owner_id = _register_and_login("t13@test.io", name="Owner T13")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], status="approved")
    _make_testimonial(space["_id"], status="approved")
    _make_testimonial(space["_id"], status="approved")
    _make_testimonial(space["_id"], status="pending")

    data = client.get("/api/analytics/overview").json()
    assert data["status_distribution"]["approved"] == 3


def test_14_rejected_count_is_correct():
    """14. Rejected status count is correct."""
    owner_id = _register_and_login("t14@test.io", name="Owner T14")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], status="rejected")
    _make_testimonial(space["_id"], status="approved")

    data = client.get("/api/analytics/overview").json()
    assert data["status_distribution"]["rejected"] == 1


def test_15_archived_count_is_correct():
    """15. Archived status count is correct."""
    owner_id = _register_and_login("t15@test.io", name="Owner T15")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], status="archived")
    _make_testimonial(space["_id"], status="archived")
    _make_testimonial(space["_id"], status="approved")

    data = client.get("/api/analytics/overview").json()
    assert data["status_distribution"]["archived"] == 2


def test_16_featured_count_is_correct():
    """16. Featured reviews count is correct."""
    owner_id = _register_and_login("t16@test.io", name="Owner T16")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], status="approved", is_featured=True)
    _make_testimonial(space["_id"], status="approved", is_featured=True)
    _make_testimonial(space["_id"], status="approved", is_featured=False)
    _make_testimonial(space["_id"], status="pending", is_featured=False)

    data = client.get("/api/analytics/overview").json()
    assert data["featured_reviews"] == 2


def test_17_space_specific_filtering_works():
    """17. Space-specific filtering correctly scopes statistics."""
    owner_id = _register_and_login("t17@test.io", name="Owner T17")
    space_a = _make_space(owner_id, name="Space 17A")
    space_b = _make_space(owner_id, name="Space 17B")

    _make_testimonial(space_a["_id"], rating=5, status="approved")
    _make_testimonial(space_a["_id"], rating=5, status="approved")
    _make_testimonial(space_b["_id"], rating=1, status="pending")

    space_a_id = str(space_a["_id"])
    res = client.get(f"/api/analytics/overview?space_id={space_a_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total_reviews"] == 2
    assert data["status_distribution"]["approved"] == 2
    assert data["status_distribution"]["pending"] == 0
    assert data["scope"] == space_a_id
    assert data["space_name"] == "Space 17A"


def test_18_all_spaces_aggregation_works():
    """18. No space_id param aggregates statistics across all owned Spaces."""
    owner_id = _register_and_login("t18@test.io", name="Owner T18")
    space_a = _make_space(owner_id, name="Agg Space A")
    space_b = _make_space(owner_id, name="Agg Space B")

    _make_testimonial(space_a["_id"], status="approved", rating=5)
    _make_testimonial(space_a["_id"], status="pending", rating=4)
    _make_testimonial(space_b["_id"], status="approved", rating=3)
    _make_testimonial(space_b["_id"], status="rejected", rating=2)

    res = client.get("/api/analytics/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["total_reviews"] == 4
    assert data["total_spaces"] == 2
    assert data["scope"] == "all"
    assert data["status_distribution"]["approved"] == 2
    assert data["status_distribution"]["pending"] == 1
    assert data["status_distribution"]["rejected"] == 1


def test_19_zero_review_space_no_division_by_zero():
    """19. Zero-review Space returns safe analytics without division by zero."""
    owner_id = _register_and_login("t19@test.io", name="Owner T19")
    _make_space(owner_id, name="Empty Space")

    res = client.get("/api/analytics/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["total_reviews"] == 0
    assert data["average_rating"] is None
    assert data["star_distribution"]["star_5"] == 0
    assert data["star_distribution"]["star_1"] == 0
    assert data["status_distribution"]["approved"] == 0


def test_20_star_distribution_missing_ratings_show_zero():
    """20. Stars with zero reviews still appear in distribution."""
    owner_id = _register_and_login("t20@test.io", name="Owner T20")
    space = _make_space(owner_id)
    _make_testimonial(space["_id"], rating=5)

    data = client.get("/api/analytics/overview").json()
    dist = data["star_distribution"]
    assert dist["star_5"] == 1
    assert dist["star_4"] == 0
    assert dist["star_3"] == 0
    assert dist["star_2"] == 0
    assert dist["star_1"] == 0


def test_21_average_rating_rounded_to_one_decimal():
    """21. Average rating is rounded to one decimal place."""
    owner_id = _register_and_login("t21@test.io", name="Owner T21")
    space = _make_space(owner_id)
    # Ratings: 5, 4, 5 = 14/3 = 4.666... → rounds to 4.7
    _make_testimonial(space["_id"], rating=5)
    _make_testimonial(space["_id"], rating=4)
    _make_testimonial(space["_id"], rating=5)

    data = client.get("/api/analytics/overview").json()
    assert data["average_rating"] == 4.7


def test_22_analytics_total_spaces_count():
    """22. total_spaces reflects the number of owned spaces."""
    owner_id = _register_and_login("t22@test.io", name="Owner T22")
    _make_space(owner_id, name="Space One")
    _make_space(owner_id, name="Space Two")
    _make_space(owner_id, name="Space Three")

    data = client.get("/api/analytics/overview").json()
    assert data["total_spaces"] == 3


def test_23_space_filter_returns_404_for_nonexistent_space():
    """23. Analytics request for a non-existent space_id returns 404."""
    _register_and_login("t23@test.io", name="Owner T23")
    fake_id = str(ObjectId())
    res = client.get(f"/api/analytics/overview?space_id={fake_id}")
    assert res.status_code == 404


def test_24_owner_without_spaces_returns_zeros():
    """24. Owner with no Spaces at all gets clean zero analytics."""
    _register_and_login("t24@test.io", name="Owner T24")
    # No spaces created

    res = client.get("/api/analytics/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["total_reviews"] == 0
    assert data["total_spaces"] == 0
    assert data["average_rating"] is None
    assert data["featured_reviews"] == 0
