import io
from datetime import datetime, timezone
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


# Mock in-memory DB store for spaces and testimonials
class MockSpacesDB:
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


test_db = MockSpacesDB()


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
            elif "token_id" in query:
                doc = test_db.auth_sessions.get(query["token_id"])
                if doc and "$set" in update:
                    doc.update(update["$set"])

    class AsyncSpacesColl:
        async def find_one(self, query):
            if "_id" in query:
                sid = str(query["_id"])
                doc = test_db.spaces.get(sid)
                if doc:
                    return doc
                return None
            if "slug" in query:
                slug_val = query["slug"]
                exclude_id = str(query.get("_id", {}).get("$ne", "")) if isinstance(query.get("_id"), dict) else ""
                for s in test_db.spaces.values():
                    if s["slug"] == slug_val and str(s["_id"]) != exclude_id:
                        return s
                return None
            return None

        def find(self, query):
            owner_id = query.get("owner_id")
            results = [s for s in test_db.spaces.values() if s.get("owner_id") == owner_id]

            class Cursor:
                def __init__(self, data):
                    self.data = data

                def sort(self, key, direction):
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
            test_db.spaces[doc_id] = doc
            class Res:
                inserted_id = doc["_id"]
            return Res()

        async def update_one(self, query, update):
            if "_id" in query:
                sid = str(query["_id"])
                if sid in test_db.spaces:
                    if "$set" in update:
                        test_db.spaces[sid].update(update["$set"])

        async def delete_one(self, query):
            if "_id" in query:
                sid = str(query["_id"])
                test_db.spaces.pop(sid, None)

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

    class AsyncTestimonialsColl:
        async def delete_many(self, query):
            keys_to_del = []
            for tid, tdoc in test_db.testimonials.items():
                if "$or" in query:
                    for cond in query["$or"]:
                        if str(tdoc.get("space_id")) == str(cond.get("space_id")):
                            keys_to_del.append(tid)
                            break
            for k in keys_to_del:
                test_db.testimonials.pop(k, None)

    monkeypatch.setattr("backend.app.api.spaces.get_spaces_collection", lambda: AsyncSpacesColl())
    monkeypatch.setattr("backend.app.api.spaces.get_testimonials_collection", lambda: AsyncTestimonialsColl())
    monkeypatch.setattr("backend.app.api.auth.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.core.auth_dependency.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.api.auth.get_auth_sessions_collection", lambda: AsyncSessionsColl())
    monkeypatch.setattr("backend.app.api.auth.get_verification_tokens_collection", lambda: AsyncVerificationColl())
    monkeypatch.setattr("backend.app.api.auth.get_password_reset_tokens_collection", lambda: AsyncResetTokensColl())


def register_and_login(email: str, name: str = "Test Owner"):
    """Helper to create user and establish logged in session with cookies."""
    client.post("/api/auth/register", json={"name": name, "email": email, "password": "password123"})
    client.post("/api/auth/login", json={"email": email, "password": "password123"})


# -------------------------------------------------------------------
# 1. CREATE SPACE TESTS
# -------------------------------------------------------------------
def test_1_authenticated_owner_can_create_space():
    client.cookies.clear()
    register_and_login("owner1@example.com", "Owner One")

    res = client.post("/api/spaces", json={
        "name": "ABC Technologies",
        "slug": "abc-technologies",
        "custom_prompt": "Please leave a review for ABC Tech!",
        "avatar_enabled": True,
        "rating_enabled": True,
        "custom_questions": [{"question": "What feature did you like most?"}]
    })
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "ABC Technologies"
    assert data["slug"] == "abc-technologies"
    assert "owner_id" in data
    assert len(data["custom_questions"]) == 1


def test_2_unauthenticated_user_cannot_create_space():
    client.cookies.clear()
    res = client.post("/api/spaces", json={
        "name": "Unauthorized Space",
        "slug": "unauth-space"
    })
    assert res.status_code == 401


def test_3_space_associated_with_authenticated_owner():
    client.cookies.clear()
    register_and_login("owner_assoc@example.com")
    me_res = client.get("/api/auth/me")
    owner_id = me_res.json()["id"]

    res = client.post("/api/spaces", json={
        "name": "Owner Assoc Space",
        "slug": "owner-assoc-space"
    })
    assert res.status_code == 201
    assert res.json()["owner_id"] == owner_id


def test_4_duplicate_slug_rejected():
    client.cookies.clear()
    register_and_login("dup_slug@example.com")
    client.post("/api/spaces", json={"name": "Space One", "slug": "dup-slug-test"})

    res_dup = client.post("/api/spaces", json={"name": "Space Two", "slug": "dup-slug-test"})
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.json()["detail"].lower()


def test_5_invalid_slug_rejected():
    client.cookies.clear()
    register_and_login("invalid_slug@example.com")

    # Slug with spaces
    res1 = client.post("/api/spaces", json={"name": "Bad Slug 1", "slug": "bad slug spaces"})
    assert res1.status_code == 422 or res1.status_code == 400

    # Slug with special characters
    res2 = client.post("/api/spaces", json={"name": "Bad Slug 2", "slug": "bad@slug#123"})
    assert res2.status_code == 422 or res2.status_code == 400

    # Empty slug
    res3 = client.post("/api/spaces", json={"name": "Bad Slug 3", "slug": ""})
    assert res3.status_code == 422 or res3.status_code == 400


# -------------------------------------------------------------------
# 2. LIST OWNER SPACES & IDOR ISOLATION TESTS
# -------------------------------------------------------------------
def test_6_owner_can_list_their_spaces():
    client.cookies.clear()
    register_and_login("lister@example.com")
    client.post("/api/spaces", json={"name": "Space Alpha", "slug": "space-alpha"})
    client.post("/api/spaces", json={"name": "Space Beta", "slug": "space-beta"})

    res = client.get("/api/spaces")
    assert res.status_code == 200
    spaces = res.json()
    assert len(spaces) == 2


def test_7_owner_cannot_see_another_owners_private_spaces():
    # Owner A creates a space
    client.cookies.clear()
    register_and_login("user_a@example.com", "User A")
    client.post("/api/spaces", json={"name": "User A Private Space", "slug": "user-a-space"})

    # Owner B lists spaces -> should be empty
    client.cookies.clear()
    register_and_login("user_b@example.com", "User B")
    res_b = client.get("/api/spaces")
    assert res_b.status_code == 200
    assert len(res_b.json()) == 0


# -------------------------------------------------------------------
# 3. GET / UPDATE / DELETE & IDOR TESTS
# -------------------------------------------------------------------
def test_8_9_get_single_space_and_idor_protection():
    client.cookies.clear()
    register_and_login("owner_get@example.com")
    sp = client.post("/api/spaces", json={"name": "Get Test Space", "slug": "get-test-space"}).json()
    space_id = sp["id"]

    # Owner can get their space
    res_owner = client.get(f"/api/spaces/{space_id}")
    assert res_owner.status_code == 200
    assert res_owner.json()["name"] == "Get Test Space"

    # Other owner cannot access space (IDOR check)
    client.cookies.clear()
    register_and_login("other_get@example.com")
    res_other = client.get(f"/api/spaces/{space_id}")
    assert res_other.status_code == 403


def test_10_11_update_space_and_idor_protection():
    client.cookies.clear()
    register_and_login("updater@example.com")
    sp = client.post("/api/spaces", json={"name": "Original Name", "slug": "original-slug"}).json()
    space_id = sp["id"]

    # Update by owner
    res_update = client.put(f"/api/spaces/{space_id}", json={
        "name": "Updated Name",
        "custom_prompt": "New Custom Prompt"
    })
    assert res_update.status_code == 200
    assert res_update.json()["name"] == "Updated Name"

    # IDOR attempt: Other user tries to update -> 403
    client.cookies.clear()
    register_and_login("hacker_update@example.com")
    res_hacker = client.put(f"/api/spaces/{space_id}", json={"name": "Hacked Name"})
    assert res_hacker.status_code == 403


def test_12_13_delete_space_and_idor_protection():
    client.cookies.clear()
    register_and_login("deleter@example.com")
    sp = client.post("/api/spaces", json={"name": "Delete Space", "slug": "delete-space"}).json()
    space_id = sp["id"]

    # IDOR attempt: Other user tries to delete -> 403
    client.cookies.clear()
    register_and_login("hacker_delete@example.com")
    res_hacker = client.delete(f"/api/spaces/{space_id}")
    assert res_hacker.status_code == 403

    # Owner deletes their space -> 200
    client.cookies.clear()
    client.post("/api/auth/login", json={"email": "deleter@example.com", "password": "password123"})
    res_del = client.delete(f"/api/spaces/{space_id}")
    assert res_del.status_code == 200
    assert "deleted" in res_del.json()["message"].lower()


# -------------------------------------------------------------------
# 4. SETTINGS & CUSTOM QUESTIONS TESTS
# -------------------------------------------------------------------
def test_14_15_16_custom_questions_avatar_and_rating_settings():
    client.cookies.clear()
    register_and_login("settings@example.com")
    res = client.post("/api/spaces", json={
        "name": "Settings Space",
        "slug": "settings-space",
        "avatar_enabled": False,
        "rating_enabled": True,
        "custom_questions": [
            {"question": "How did you hear about us?"},
            {"question": "What can we improve?"}
        ]
    })
    assert res.status_code == 201
    data = res.json()
    assert data["avatar_enabled"] is False
    assert data["rating_enabled"] is True
    assert len(data["custom_questions"]) == 2
    assert data["custom_questions"][0]["question"] == "How did you hear about us?"


# -------------------------------------------------------------------
# 5. LOGO UPLOAD TESTS
# -------------------------------------------------------------------
def test_17_18_19_logo_upload_valid_invalid_and_oversized():
    client.cookies.clear()
    register_and_login("uploader@example.com")

    # Valid image upload (PNG)
    png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    res_valid = client.post(
        "/api/spaces/upload-logo",
        files={"file": ("logo.png", io.BytesIO(png_data), "image/png")}
    )
    assert res_valid.status_code == 201
    assert "logo_url" in res_valid.json()
    assert res_valid.json()["logo_url"].startswith("/uploads/spaces/")

    # Invalid image type (TXT/PDF)
    res_invalid = client.post(
        "/api/spaces/upload-logo",
        files={"file": ("doc.txt", io.BytesIO(b"hello world"), "text/plain")}
    )
    assert res_invalid.status_code == 400

    # Oversized image (> 2MB)
    big_data = b"0" * (2 * 1024 * 1024 + 100)
    res_big = client.post(
        "/api/spaces/upload-logo",
        files={"file": ("big.png", io.BytesIO(big_data), "image/png")}
    )
    assert res_big.status_code == 400


# -------------------------------------------------------------------
# 6. PUBLIC SPACE ENDPOINT TESTS
# -------------------------------------------------------------------
def test_20_21_22_public_space_endpoint():
    client.cookies.clear()
    register_and_login("public_owner@example.com")
    client.post("/api/spaces", json={
        "name": "Public Enterprise",
        "slug": "public-enterprise",
        "custom_prompt": "Tell us what you think!",
        "custom_questions": [{"question": "Would you recommend us?"}]
    })

    # Unauthenticated request to public endpoint
    client.cookies.clear()
    res_pub = client.get("/api/public/spaces/public-enterprise")
    assert res_pub.status_code == 200
    pub_data = res_pub.json()
    assert pub_data["name"] == "Public Enterprise"
    assert pub_data["slug"] == "public-enterprise"

    # Security check: owner_id and internal fields must NOT be in public response
    assert "owner_id" not in pub_data
    assert "_id" not in pub_data

    # Nonexistent slug -> 404
    res_404 = client.get("/api/public/spaces/nonexistent-slug-xyz")
    assert res_404.status_code == 404


# -------------------------------------------------------------------
# 7. REGRESSION TESTS (MODULE 0 & MODULE 2)
# -------------------------------------------------------------------
def test_24_module_2_auth_regression():
    client.cookies.clear()
    reg = client.post("/api/auth/register", json={
        "name": "Regress User", "email": "regress@example.com", "password": "password123"
    })
    assert reg.status_code == 201
    login = client.post("/api/auth/login", json={"email": "regress@example.com", "password": "password123"})
    assert login.status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 200


def test_25_module_0_health_regression():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
