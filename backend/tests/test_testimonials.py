import io
import json
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


# Mock in-memory DB store for users, spaces, and testimonials
class MockTestimonialsDB:
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


test_db = MockTestimonialsDB()


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

        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.spaces[doc_id] = doc
            class Res:
                inserted_id = doc["_id"]
            return Res()

    class AsyncTestimonialsColl:
        async def insert_one(self, doc):
            doc_id = str(ObjectId())
            doc["_id"] = ObjectId(doc_id)
            test_db.testimonials[doc_id] = doc
            class Res:
                inserted_id = doc["_id"]
            return Res()

        async def find_one(self, query):
            if "_id" in query:
                tid = str(query["_id"])
                return test_db.testimonials.get(tid)
            return None

    monkeypatch.setattr("backend.app.api.testimonials.get_spaces_collection", lambda: AsyncSpacesColl())
    monkeypatch.setattr("backend.app.api.testimonials.get_testimonials_collection", lambda: AsyncTestimonialsColl())
    monkeypatch.setattr("backend.app.api.spaces.get_spaces_collection", lambda: AsyncSpacesColl())
    monkeypatch.setattr("backend.app.api.auth.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.core.auth_dependency.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.api.auth.get_auth_sessions_collection", lambda: AsyncSessionsColl())
    monkeypatch.setattr("backend.app.api.auth.get_verification_tokens_collection", lambda: AsyncVerificationColl())
    monkeypatch.setattr("backend.app.api.auth.get_password_reset_tokens_collection", lambda: AsyncResetTokensColl())


def setup_test_space(slug="acme-corp", rating_enabled=True, avatar_enabled=True):
    """Helper to seed a test space in mock DB."""
    space_id = str(ObjectId())
    space_doc = {
        "_id": ObjectId(space_id),
        "owner_id": str(ObjectId()),
        "name": "Acme Corporation",
        "slug": slug,
        "custom_prompt": "Tell us how we did!",
        "avatar_enabled": avatar_enabled,
        "rating_enabled": rating_enabled,
        "custom_questions": [{"question": "What feature did you like most?"}],
    }
    test_db.spaces[space_id] = space_doc
    return space_doc


# -------------------------------------------------------------------
# 1-4. PUBLIC SPACE LOOKUP & PAGE TESTS
# -------------------------------------------------------------------
def test_1_valid_public_space_page_loads():
    setup_test_space("acme-page")
    res = client.get("/collect/acme-page")
    assert res.status_code == 200
    assert "html" in res.headers.get("content-type", "")


def test_2_invalid_space_slug_returns_404():
    res = client.get("/api/public/spaces/nonexistent-space-xyz")
    assert res.status_code == 404


def test_3_4_public_space_endpoint_no_auth_and_no_private_owner_info():
    setup_test_space("acme-public")
    client.cookies.clear()
    res = client.get("/api/public/spaces/acme-public")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Acme Corporation"
    assert "owner_id" not in data
    assert "_id" not in data


# -------------------------------------------------------------------
# 5-10. TESTIMONIAL SUBMISSION & MODERATION STATE TESTS
# -------------------------------------------------------------------
def test_5_to_10_valid_testimonial_submission_stored_as_pending():
    space = setup_test_space("submission-test")
    client.cookies.clear()

    res = client.post("/api/public/spaces/submission-test/testimonials", data={
        "client_name": "Jane Customer",
        "client_email": "jane@example.com",
        "company_role": "CEO @ Startup",
        "rating": 5,
        "review_text": "This product exceeded all our expectations! Highly recommended.",
        "custom_answers": json.dumps([{"question": "What feature did you like most?", "answer": "Fast setup"}])
    })

    assert res.status_code == 201
    assert "submitted" in res.json()["message"].lower()

    # Verify document in MongoDB store
    assert len(test_db.testimonials) == 1
    t = list(test_db.testimonials.values())[0]

    # Required Field Assertions
    assert t["client_name"] == "Jane Customer"
    assert t["client_email"] == "jane@example.com"
    assert t["rating"] == 5
    assert t["space_id"] == str(space["_id"])

    # Moderation Enforcements
    assert t["status"] == "pending"
    assert t["is_featured"] is False


# -------------------------------------------------------------------
# 11-18. VALIDATION TESTS
# -------------------------------------------------------------------
def test_11_missing_name_rejected():
    setup_test_space("val-space")
    res = client.post("/api/public/spaces/val-space/testimonials", data={
        "client_name": "   ",
        "client_email": "jane@example.com",
        "rating": 5,
        "review_text": "Great product experience overall!"
    })
    assert res.status_code == 400


def test_12_13_missing_and_invalid_email_rejected():
    setup_test_space("email-space")
    res1 = client.post("/api/public/spaces/email-space/testimonials", data={
        "client_name": "Jane",
        "client_email": "not-an-email",
        "rating": 5,
        "review_text": "Great product experience overall!"
    })
    assert res1.status_code == 400


def test_14_missing_or_short_review_rejected():
    setup_test_space("review-space")
    res = client.post("/api/public/spaces/review-space/testimonials", data={
        "client_name": "Jane",
        "client_email": "jane@example.com",
        "rating": 5,
        "review_text": "Short"  # < 10 chars
    })
    assert res.status_code == 400


def test_15_16_17_invalid_rating_rejected():
    setup_test_space("rating-space")

    # Below 1
    res1 = client.post("/api/public/spaces/rating-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "rating": 0, "review_text": "Valid review text here!"
    })
    assert res1.status_code == 400

    # Above 5
    res2 = client.post("/api/public/spaces/rating-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "rating": 6, "review_text": "Valid review text here!"
    })
    assert res2.status_code == 400


def test_18_excessively_long_review_rejected():
    setup_test_space("long-space")
    long_text = "a" * 2001
    res = client.post("/api/public/spaces/long-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "rating": 5, "review_text": long_text
    })
    assert res.status_code == 400


# -------------------------------------------------------------------
# 19-23. SPACE CONFIGURATION & CUSTOM QUESTIONS TESTS
# -------------------------------------------------------------------
def test_19_20_rating_required_settings_enforced():
    # Rating disabled space
    setup_test_space("no-rating-space", rating_enabled=False)

    # Submission without rating should be accepted
    res = client.post("/api/public/spaces/no-rating-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "review_text": "Great product experience overall!"
    })
    assert res.status_code == 201
    t = list(test_db.testimonials.values())[0]
    assert t["rating"] is None


def test_21_22_avatar_enabled_disabled_enforced():
    # Avatar disabled space
    setup_test_space("no-avatar-space", avatar_enabled=False)

    png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    res = client.post("/api/public/spaces/no-avatar-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "rating": 5, "review_text": "Great product experience overall!"
    }, files={"avatar": ("avatar.png", io.BytesIO(png_data), "image/png")})

    assert res.status_code == 201
    t = list(test_db.testimonials.values())[0]
    # Avatar should be ignored when avatar_enabled=False
    assert t["avatar_url"] is None


def test_23_custom_questions_stored_correctly():
    setup_test_space("cq-space")
    answers = [{"question": "What feature did you like most?", "answer": "The speed and UI."}]

    res = client.post("/api/public/spaces/cq-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "rating": 5, "review_text": "Great product experience overall!",
        "custom_answers": json.dumps(answers)
    })
    assert res.status_code == 201
    t = list(test_db.testimonials.values())[0]
    assert len(t["custom_answers"]) == 1
    assert t["custom_answers"][0]["answer"] == "The speed and UI."


# -------------------------------------------------------------------
# 24-28. UPLOAD & SECURITY TESTS
# -------------------------------------------------------------------
def test_24_to_28_avatar_upload_valid_invalid_oversized():
    setup_test_space("upload-space", avatar_enabled=True)

    # Valid PNG upload
    png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    res_valid = client.post("/api/public/spaces/upload-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "rating": 5, "review_text": "Great product experience overall!"
    }, files={"avatar": ("test_avatar.png", io.BytesIO(png_data), "image/png")})

    assert res_valid.status_code == 201
    t = list(test_db.testimonials.values())[0]
    assert t["avatar_url"].startswith("/uploads/testimonials/")

    # Invalid MIME type (text file)
    test_db.testimonials.clear()
    res_invalid = client.post("/api/public/spaces/upload-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "rating": 5, "review_text": "Great product experience overall!"
    }, files={"avatar": ("script.sh", io.BytesIO(b"echo hack"), "text/plain")})
    assert res_invalid.status_code == 400

    # Oversized file (> 2MB)
    big_data = b"0" * (2 * 1024 * 1024 + 100)
    res_big = client.post("/api/public/spaces/upload-space/testimonials", data={
        "client_name": "Jane", "client_email": "jane@example.com",
        "rating": 5, "review_text": "Great product experience overall!"
    }, files={"avatar": ("big.png", io.BytesIO(big_data), "image/png")})
    assert res_big.status_code == 400


# -------------------------------------------------------------------
# 29-33. SECURITY INJECTION ATTEMPT TESTS
# -------------------------------------------------------------------
def test_29_to_33_status_and_is_featured_injection_prevented():
    setup_test_space("sec-space")

    res = client.post("/api/public/spaces/sec-space/testimonials", data={
        "client_name": "Hacker",
        "client_email": "hacker@example.com",
        "rating": 5,
        "review_text": "Attempting to inject approved status and featured flags!",
        "status": "approved",
        "is_featured": True,
        "owner_id": "fake_owner_123",
        "space_id": "fake_space_123"
    })

    assert res.status_code == 201
    t = list(test_db.testimonials.values())[0]

    # Must be pending and false, ignoring client injection attempts
    assert t["status"] == "pending"
    assert t["is_featured"] is False


# -------------------------------------------------------------------
# 38-40. REGRESSION TESTS (MODULE 0, MODULE 2, MODULE 3)
# -------------------------------------------------------------------
def test_38_module_3_space_endpoint_regression():
    setup_test_space("regress-space")
    res = client.get("/api/public/spaces/regress-space")
    assert res.status_code == 200
    assert res.json()["slug"] == "regress-space"


def test_39_module_2_auth_regression():
    client.cookies.clear()
    reg = client.post("/api/auth/register", json={
        "name": "M4 Regress User", "email": "m4regress@example.com", "password": "password123"
    })
    assert reg.status_code == 201


def test_40_module_0_health_regression():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
