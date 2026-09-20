from datetime import datetime, timezone
import re
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.testimonial import TestimonialStatus

client = TestClient(app)


class MockModerationDB:
    def __init__(self):
        self.users = {}
        self.email_verification_tokens = {}
        self.auth_sessions = {}
        self.password_reset_tokens = {}
        self.spaces = {}
        self.testimonials = {}

    def clear(self):
        self.users.clear()
        self.email_verification_tokens.clear()
        self.auth_sessions.clear()
        self.password_reset_tokens.clear()
        self.spaces.clear()
        self.testimonials.clear()


test_db = MockModerationDB()


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
                uid = str(query["_id"])
                return test_db.users.get(uid)
            if "email" in query:
                email = query["email"]
                for u in test_db.users.values():
                    if u["email"] == email:
                        return u
            return None

        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.users[doc_id] = doc
            class Res:
                inserted_id = doc["_id"]
            return Res()

        async def update_one(self, query, update):
            if "_id" in query:
                uid = str(query["_id"])
                if uid in test_db.users:
                    if "$set" in update:
                        test_db.users[uid].update(update["$set"])

    class AsyncSessionsColl:
        async def find_one(self, query):
            if "token_id" in query:
                return test_db.auth_sessions.get(query["token_id"])
            return None

        async def insert_one(self, doc):
            doc["_id"] = str(ObjectId())
            test_db.auth_sessions[doc["token_id"]] = doc

        async def update_one(self, query, update):
            if "_id" in query:
                target_id = str(query["_id"])
                for doc in test_db.auth_sessions.values():
                    if str(doc.get("_id", "")) == target_id:
                        if "$set" in update:
                            doc.update(update["$set"])

    class AsyncVerificationColl:
        async def find_one(self, query):
            if "token" in query:
                return test_db.email_verification_tokens.get(query["token"])
            return None

        async def insert_one(self, doc):
            doc["_id"] = str(ObjectId())
            test_db.email_verification_tokens[doc["token"]] = doc

        async def update_one(self, query, update):
            if "_id" in query:
                target_id = str(query["_id"])
                for doc in test_db.email_verification_tokens.values():
                    if str(doc.get("_id", "")) == target_id:
                        if "$set" in update:
                            doc.update(update["$set"])

    class AsyncResetTokensColl:
        async def find_one(self, query):
            if "token" in query:
                return test_db.password_reset_tokens.get(query["token"])
            return None

        async def insert_one(self, doc):
            doc["_id"] = str(ObjectId())
            test_db.password_reset_tokens[doc["token"]] = doc

        async def update_one(self, query, update):
            if "_id" in query:
                for doc in test_db.password_reset_tokens.values():
                    if doc.get("_id") == query["_id"]:
                        if "$set" in update:
                            doc.update(update["$set"])

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
            class Res:
                inserted_id = doc["_id"]
            return Res()

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
                tid = str(query["_id"])
                return test_db.testimonials.get(tid)
            return None

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

                # Filter rating
                if "rating" in query:
                    if tdoc.get("rating") != query["rating"]:
                        continue

                # Filter search keyword ($or)
                if "$or" in query:
                    matched = False
                    for cond in query["$or"]:
                        for field, reg in cond.items():
                            val = str(tdoc.get(field) or "")
                            pattern = reg.get("$regex", "")
                            if pattern and re.search(pattern, val, re.IGNORECASE):
                                matched = True
                                break
                        if matched:
                            break
                    if not matched:
                        continue

                results.append(dict(tdoc))

            class Cursor:
                def __init__(self, data):
                    self.data = data

                def sort(self, key, direction=1):
                    reverse = direction < 0
                    try:
                        self.data.sort(key=lambda d: d.get(key) or "", reverse=reverse)
                    except Exception:
                        pass
                    return self

                def skip(self, count):
                    self.data = self.data[count:]
                    return self

                def limit(self, count):
                    self.data = self.data[:count]
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

        async def count_documents(self, query, *args, **kwargs):
            cursor = self.find(query)
            return len(cursor.data)

        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.testimonials[doc_id] = doc
            class Res:
                inserted_id = doc["_id"]
            return Res()

        async def update_one(self, query, update):
            if "_id" in query:
                tid = str(query["_id"])
                if tid in test_db.testimonials:
                    if "$set" in update:
                        test_db.testimonials[tid].update(update["$set"])

    # Patch in all relevant modules
    monkeypatch.setattr("backend.app.api.owner_testimonials.get_spaces_collection", lambda: AsyncSpacesColl())
    monkeypatch.setattr("backend.app.api.owner_testimonials.get_testimonials_collection", lambda: AsyncTestimonialsColl())
    monkeypatch.setattr("backend.app.api.spaces.get_spaces_collection", lambda: AsyncSpacesColl())
    monkeypatch.setattr("backend.app.api.spaces.get_testimonials_collection", lambda: AsyncTestimonialsColl())
    monkeypatch.setattr("backend.app.api.testimonials.get_spaces_collection", lambda: AsyncSpacesColl())
    monkeypatch.setattr("backend.app.api.testimonials.get_testimonials_collection", lambda: AsyncTestimonialsColl())
    monkeypatch.setattr("backend.app.api.auth.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.core.auth_dependency.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.api.auth.get_auth_sessions_collection", lambda: AsyncSessionsColl())
    monkeypatch.setattr("backend.app.api.auth.get_verification_tokens_collection", lambda: AsyncVerificationColl())
    monkeypatch.setattr("backend.app.api.auth.get_password_reset_tokens_collection", lambda: AsyncResetTokensColl())


def register_and_login(email: str, name: str = "Test Owner"):
    """Helper to create user, verify email, and log in."""
    reg = client.post("/api/auth/register", json={"name": name, "email": email, "password": "SecurePassword123!"})
    token = reg.json().get("dev_verification_token")
    if token:
        client.post("/api/auth/verify-email", json={"token": token})
    client.post("/api/auth/login", json={"email": email, "password": "SecurePassword123!"})


def create_space_helper(slug: str = "demo-space", name: str = "Demo Space"):
    """Helper to create a space for current logged in owner."""
    res = client.post("/api/spaces", json={
        "name": name,
        "slug": slug,
        "custom_prompt": "Please leave feedback!",
        "avatar_enabled": True,
        "rating_enabled": True,
        "custom_questions": []
    })
    return res.json()


def submit_testimonial_helper(space_slug: str, name: str = "John Doe", email: str = "john@example.com", role: str = "Engineer", rating: int = 5, text: str = "Incredible product and great experience!"):
    """Helper to publicly submit a testimonial."""
    return client.post(
        f"/api/public/spaces/{space_slug}/testimonials",
        data={
            "client_name": name,
            "client_email": email,
            "company_role": role,
            "rating": rating,
            "review_text": text
        }
    )


# -----------------------------------------------------------------------------
# MODULE 5 REVIEW MODERATION TESTS
# -----------------------------------------------------------------------------

def test_1_authenticated_owner_can_retrieve_own_testimonials():
    client.cookies.clear()
    register_and_login("owner1@test.com", "Owner 1")
    space = create_space_helper("space-one", "Space One")
    submit_testimonial_helper("space-one", "Alice", "alice@example.com", "CTO", 5, "Amazing experience!")

    res = client.get("/api/testimonials")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["client_name"] == "Alice"
    assert data["items"][0]["space_name"] == "Space One"
    assert data["items"][0]["status"] == "pending"
    assert data["items"][0]["is_featured"] is False


def test_2_unauthenticated_user_cannot_access_moderation():
    client.cookies.clear()
    res = client.get("/api/testimonials")
    assert res.status_code == 401

    patch_res = client.patch(f"/api/testimonials/{ObjectId()}/status", json={"status": "approved"})
    assert patch_res.status_code == 401

    feat_res = client.patch(f"/api/testimonials/{ObjectId()}/featured", json={"is_featured": True})
    assert feat_res.status_code == 401


def test_3_owner_can_approve_testimonial():
    client.cookies.clear()
    register_and_login("owner2@test.com", "Owner 2")
    create_space_helper("space-two", "Space Two")
    submit_testimonial_helper("space-two", "Bob", "bob@example.com", "Manager", 5, "Loved using this software!")

    list_res = client.get("/api/testimonials")
    t_id = list_res.json()["items"][0]["id"]

    approve_res = client.patch(f"/api/testimonials/{t_id}/status", json={"status": "approved"})
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"
    assert approve_res.json()["id"] == t_id


def test_4_owner_can_reject_testimonial():
    client.cookies.clear()
    register_and_login("owner3@test.com", "Owner 3")
    create_space_helper("space-three", "Space Three")
    submit_testimonial_helper("space-three", "Charlie", "charlie@example.com", "Analyst", 1, "Did not enjoy it at all.")

    list_res = client.get("/api/testimonials")
    t_id = list_res.json()["items"][0]["id"]

    reject_res = client.patch(f"/api/testimonials/{t_id}/status", json={"status": "rejected"})
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"

    # Should appear under rejected filter and not under pending
    pending_res = client.get("/api/testimonials?status=pending")
    assert pending_res.json()["total"] == 0

    rejected_res = client.get("/api/testimonials?status=rejected")
    assert rejected_res.json()["total"] == 1


def test_5_owner_can_archive_testimonial():
    client.cookies.clear()
    register_and_login("owner4@test.com", "Owner 4")
    create_space_helper("space-four", "Space Four")
    submit_testimonial_helper("space-four", "Diana", "diana@example.com", "Director", 4, "Solid product overall.")

    list_res = client.get("/api/testimonials")
    t_id = list_res.json()["items"][0]["id"]

    archive_res = client.patch(f"/api/testimonials/{t_id}/status", json={"status": "archived"})
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "archived"

    archived_res = client.get("/api/testimonials?status=archived")
    assert archived_res.json()["total"] == 1


def test_6_owner_can_feature_and_unfeature_testimonial():
    client.cookies.clear()
    register_and_login("owner5@test.com", "Owner 5")
    create_space_helper("space-five", "Space Five")
    submit_testimonial_helper("space-five", "Eva", "eva@example.com", "VP", 5, "Outstanding service and results.")

    list_res = client.get("/api/testimonials")
    t_id = list_res.json()["items"][0]["id"]

    # Feature
    feat_res = client.patch(f"/api/testimonials/{t_id}/featured", json={"is_featured": True})
    assert feat_res.status_code == 200
    assert feat_res.json()["is_featured"] is True

    # Unfeature
    unfeat_res = client.patch(f"/api/testimonials/{t_id}/featured", json={"is_featured": False})
    assert unfeat_res.status_code == 200
    assert unfeat_res.json()["is_featured"] is False


def test_7_owner_can_search_testimonials():
    client.cookies.clear()
    register_and_login("owner6@test.com", "Owner 6")
    create_space_helper("space-six", "Space Six")
    submit_testimonial_helper("space-six", "Rahul Sharma", "rahul@abc.com", "Lead Dev", 5, "Fastest setup ever.")
    submit_testimonial_helper("space-six", "Michael Scott", "michael@dunder.com", "Regional Manager", 4, "That's what she said.")

    search_res = client.get("/api/testimonials?search=Rahul")
    assert search_res.status_code == 200
    data = search_res.json()
    assert data["total"] == 1
    assert data["items"][0]["client_name"] == "Rahul Sharma"

    # Search by email
    search_email = client.get("/api/testimonials?search=dunder.com")
    assert search_email.json()["total"] == 1
    assert search_email.json()["items"][0]["client_name"] == "Michael Scott"


def test_8_owner_can_filter_by_rating():
    client.cookies.clear()
    register_and_login("owner7@test.com", "Owner 7")
    create_space_helper("space-seven", "Space Seven")
    submit_testimonial_helper("space-seven", "User 5Star", "u5@test.com", "Dev", 5, "Five stars product!")
    submit_testimonial_helper("space-seven", "User 3Star", "u3@test.com", "Dev", 3, "Average product.")

    r5 = client.get("/api/testimonials?rating=5")
    assert r5.json()["total"] == 1
    assert r5.json()["items"][0]["rating"] == 5

    r3 = client.get("/api/testimonials?rating=3")
    assert r3.json()["total"] == 1
    assert r3.json()["items"][0]["rating"] == 3


def test_9_owner_can_filter_by_status():
    client.cookies.clear()
    register_and_login("owner8@test.com", "Owner 8")
    create_space_helper("space-eight", "Space Eight")
    submit_testimonial_helper("space-eight", "Review Pending", "p@test.com", "Role", 5, "Great pending review!")
    submit_testimonial_helper("space-eight", "Review Approved", "a@test.com", "Role", 5, "Great approved review!")

    list_res = client.get("/api/testimonials")
    appr_id = [x["id"] for x in list_res.json()["items"] if x["client_name"] == "Review Approved"][0]
    client.patch(f"/api/testimonials/{appr_id}/status", json={"status": "approved"})

    p_res = client.get("/api/testimonials?status=pending")
    assert p_res.json()["total"] == 1
    assert p_res.json()["items"][0]["client_name"] == "Review Pending"

    a_res = client.get("/api/testimonials?status=approved")
    assert a_res.json()["total"] == 1
    assert a_res.json()["items"][0]["client_name"] == "Review Approved"


def test_10_owner_can_filter_by_space():
    client.cookies.clear()
    register_and_login("owner9@test.com", "Owner 9")
    sp_a = create_space_helper("space-alpha", "Space Alpha")
    sp_b = create_space_helper("space-beta", "Space Beta")

    submit_testimonial_helper("space-alpha", "Alpha Customer", "a@alpha.com", "Alpha Role", 5, "Alpha feedback text.")
    submit_testimonial_helper("space-beta", "Beta Customer", "b@beta.com", "Beta Role", 4, "Beta feedback text.")

    res_a = client.get(f"/api/testimonials?space_id={sp_a['id']}")
    assert res_a.json()["total"] == 1
    assert res_a.json()["items"][0]["client_name"] == "Alpha Customer"

    res_b = client.get(f"/api/testimonials?space_id={sp_b['id']}")
    assert res_b.json()["total"] == 1
    assert res_b.json()["items"][0]["client_name"] == "Beta Customer"


def test_11_combined_filters_work():
    client.cookies.clear()
    register_and_login("owner10@test.com", "Owner 10")
    create_space_helper("space-ten", "Space Ten")

    submit_testimonial_helper("space-ten", "Rahul Sharma", "rahul@gmail.com", "PM", 5, "Great pending review 1.")
    submit_testimonial_helper("space-ten", "Rahul Sharma", "rahul2@gmail.com", "PM", 4, "Great pending review 2.")
    submit_testimonial_helper("space-ten", "Priya Singh", "priya@gmail.com", "PM", 5, "Great pending review 3.")

    # Status=pending + Rating=5 + search="Rahul"
    res = client.get("/api/testimonials?status=pending&rating=5&search=Rahul")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["client_name"] == "Rahul Sharma"
    assert data["items"][0]["rating"] == 5


def test_12_pagination_works():
    client.cookies.clear()
    register_and_login("owner11@test.com", "Owner 11")
    create_space_helper("space-eleven", "Space Eleven")

    for i in range(5):
        submit_testimonial_helper("space-eleven", f"Client {i}", f"c{i}@test.com", "User", 5, f"Review content number {i}!")

    p1 = client.get("/api/testimonials?page=1&limit=2")
    assert p1.status_code == 200
    d1 = p1.json()
    assert d1["total"] == 5
    assert d1["pages"] == 3
    assert len(d1["items"]) == 2
    assert d1["page"] == 1

    p2 = client.get("/api/testimonials?page=2&limit=2")
    assert len(p2.json()["items"]) == 2
    assert p2.json()["page"] == 2

    p3 = client.get("/api/testimonials?page=3&limit=2")
    assert len(p3.json()["items"]) == 1
    assert p3.json()["page"] == 3


def test_13_idor_owner_cannot_moderate_another_owners_testimonial():
    client.cookies.clear()
    # Owner A creates space and gets testimonial
    register_and_login("ownerA@test.com", "Owner A")
    create_space_helper("space-owner-a", "Space A")
    submit_testimonial_helper("space-owner-a", "Target Client", "t@client.com", "User", 5, "Private feedback for A.")

    t_list = client.get("/api/testimonials").json()
    t_id = t_list["items"][0]["id"]

    # Owner B logs in
    client.cookies.clear()
    register_and_login("ownerB@test.com", "Owner B")

    # Owner B tries to access single testimonial of Owner A -> 403 Forbidden
    get_res = client.get(f"/api/testimonials/{t_id}")
    assert get_res.status_code == 403

    # Owner B tries to approve Owner A's testimonial -> 403 Forbidden
    patch_res = client.patch(f"/api/testimonials/{t_id}/status", json={"status": "approved"})
    assert patch_res.status_code == 403

    # Owner B tries to feature Owner A's testimonial -> 403 Forbidden
    feat_res = client.patch(f"/api/testimonials/{t_id}/featured", json={"is_featured": True})
    assert feat_res.status_code == 403


def test_14_customer_cannot_perform_moderation():
    client.cookies.clear()
    # Unauthenticated / customer cannot call status patch
    res = client.patch(f"/api/testimonials/{ObjectId()}/status", json={"status": "approved"})
    assert res.status_code == 401


def test_15_newly_submitted_testimonial_remains_pending():
    client.cookies.clear()
    register_and_login("owner15@test.com", "Owner 15")
    create_space_helper("space-fifteen", "Space Fifteen")

    sub_res = submit_testimonial_helper("space-fifteen", "New Client", "new@client.com", "Buyer", 5, "Just submitted this review!")
    assert sub_res.status_code == 201

    list_res = client.get("/api/testimonials")
    assert list_res.json()["items"][0]["status"] == "pending"
    assert list_res.json()["items"][0]["is_featured"] is False


def test_16_invalid_status_rejected():
    client.cookies.clear()
    register_and_login("owner16@test.com", "Owner 16")
    create_space_helper("space-sixteen", "Space Sixteen")
    submit_testimonial_helper("space-sixteen", "Client", "c@test.com", "Role", 5, "Valid review text.")

    t_id = client.get("/api/testimonials").json()["items"][0]["id"]
    res = client.patch(f"/api/testimonials/{t_id}/status", json={"status": "invalid_status"})
    assert res.status_code == 400


def test_17_moderation_stats_accurate():
    client.cookies.clear()
    register_and_login("owner17@test.com", "Owner 17")
    create_space_helper("space-stats-1", "Stats Space 1")
    create_space_helper("space-stats-2", "Stats Space 2")

    submit_testimonial_helper("space-stats-1", "C1", "c1@test.com", "R", 5, "Review 1 text content.")
    submit_testimonial_helper("space-stats-1", "C2", "c2@test.com", "R", 4, "Review 2 text content.")
    submit_testimonial_helper("space-stats-2", "C3", "c3@test.com", "R", 5, "Review 3 text content.")

    items = client.get("/api/testimonials").json()["items"]
    # Approve one
    client.patch(f"/api/testimonials/{items[0]['id']}/status", json={"status": "approved"})
    # Feature it
    client.patch(f"/api/testimonials/{items[0]['id']}/featured", json={"is_featured": True})
    # Reject one
    client.patch(f"/api/testimonials/{items[1]['id']}/status", json={"status": "rejected"})

    stats_res = client.get("/api/testimonials/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_spaces"] == 2
    assert stats["total_reviews"] == 3
    assert stats["pending_reviews"] == 1
    assert stats["approved_reviews"] == 1
    assert stats["rejected_reviews"] == 1
    assert stats["archived_reviews"] == 0
    assert stats["featured_reviews"] == 1
