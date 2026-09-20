"""
Auth API Tests — Real Email Verification System

All email sending is mocked to (True, None) so tests are deterministic.
Tokens are stored by hash; tests use hash_token() to look them up in the mock DB.
"""

from datetime import datetime, timedelta, timezone
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from backend.app.main import app

client = TestClient(app)


# ─── In-memory mock database ─────────────────────────────────────────────────

class MockAuthDB:
    def __init__(self):
        self.users: dict = {}
        # keyed by token_hash
        self.email_verification_tokens: dict = {}
        self.auth_sessions: dict = {}
        # keyed by token_hash
        self.password_reset_tokens: dict = {}

    def clear(self):
        self.users.clear()
        self.email_verification_tokens.clear()
        self.auth_sessions.clear()
        self.password_reset_tokens.clear()


test_db = MockAuthDB()


@pytest.fixture(autouse=True)
def setup_and_teardown():
    test_db.clear()
    yield
    test_db.clear()


# ─── MongoDB collection mocks ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_mongo_collections(monkeypatch):
    class AsyncUsersColl:
        async def find_one(self, query):
            if "_id" in query:
                uid = str(query["_id"])
                return test_db.users.get(uid)
            if "email" in query:
                for u in test_db.users.values():
                    if u["email"] == query["email"]:
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
                if uid in test_db.users and "$set" in update:
                    test_db.users[uid].update(update["$set"])

        async def count_documents(self, query):
            if not query:
                return len(test_db.users)
            count = 0
            for u in test_db.users.values():
                match = all(u.get(k) == v for k, v in query.items())
                if match:
                    count += 1
            return count

        async def update_many(self, query, update):
            for uid, u in test_db.users.items():
                if "$set" in update:
                    u.update(update["$set"])

    class AsyncVerificationColl:
        """Keyed by token_hash internally."""

        async def find_one(self, query):
            if "token_hash" in query:
                return test_db.email_verification_tokens.get(query["token_hash"])
            return None

        async def insert_one(self, doc):
            doc["_id"] = str(ObjectId())
            # keyed by token_hash
            test_db.email_verification_tokens[doc["token_hash"]] = doc

        async def update_one(self, query, update):
            if "_id" in query:
                target_id = str(query["_id"])
                for doc in test_db.email_verification_tokens.values():
                    if str(doc.get("_id", "")) == target_id:
                        if "$set" in update:
                            doc.update(update["$set"])

        async def update_many(self, query, update):
            uid = query.get("user_id")
            for doc in test_db.email_verification_tokens.values():
                if uid and doc.get("user_id") != uid:
                    continue
                if "used" in query and doc.get("used") != query["used"]:
                    continue
                if "$set" in update:
                    doc.update(update["$set"])

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

        async def update_many(self, query, update):
            uid = query.get("user_id")
            is_revoked = query.get("is_revoked")
            for doc in test_db.auth_sessions.values():
                if uid and doc.get("user_id") != uid:
                    continue
                if is_revoked is not None and doc.get("is_revoked") != is_revoked:
                    continue
                if "$set" in update:
                    doc.update(update["$set"])

    class AsyncResetTokensColl:
        """Keyed by token_hash internally."""

        async def find_one(self, query):
            if "token_hash" in query:
                return test_db.password_reset_tokens.get(query["token_hash"])
            return None

        async def insert_one(self, doc):
            doc["_id"] = str(ObjectId())
            test_db.password_reset_tokens[doc["token_hash"]] = doc

        async def update_one(self, query, update):
            if "_id" in query:
                for doc in test_db.password_reset_tokens.values():
                    if doc.get("_id") == query["_id"]:
                        if "$set" in update:
                            doc.update(update["$set"])

        async def update_many(self, query, update):
            uid = query.get("user_id")
            for doc in test_db.password_reset_tokens.values():
                if uid and doc.get("user_id") != uid:
                    continue
                if "$set" in update:
                    doc.update(update["$set"])

    monkeypatch.setattr("backend.app.api.auth.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.core.auth_dependency.get_users_collection", lambda: AsyncUsersColl())
    monkeypatch.setattr("backend.app.api.auth.get_verification_tokens_collection", lambda: AsyncVerificationColl())
    monkeypatch.setattr("backend.app.api.auth.get_auth_sessions_collection", lambda: AsyncSessionsColl())
    monkeypatch.setattr("backend.app.api.auth.get_password_reset_tokens_collection", lambda: AsyncResetTokensColl())


# ─── Email mock (must intercept the actual function the endpoint calls) ───────

@pytest.fixture(autouse=True)
def mock_email(monkeypatch):
    """Stub out SMTP so tests never hit a real mail server."""
    monkeypatch.setattr(
        "backend.app.api.auth.send_verification_email",
        lambda to, name, token: (True, None)
    )
    monkeypatch.setattr(
        "backend.app.api.auth.send_password_reset_email",
        lambda to, name, token: (True, None)
    )


# ─── Helper: register a Gmail user ───────────────────────────────────────────

def _register(name="Alice", email="alice@gmail.com", password="securepass123"):
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password})


def _get_token_doc_for_user(user_id: str) -> dict | None:
    """Find the latest (unused) verification token for a user in the mock DB."""
    for doc in test_db.email_verification_tokens.values():
        if doc.get("user_id") == user_id and not doc.get("used", False):
            return doc
    return None


# ─── Registration Tests ───────────────────────────────────────────────────────

def test_1_successful_registration():
    res = _register()
    assert res.status_code == 201
    data = res.json()
    assert data["user"]["email"] == "alice@gmail.com"
    assert data["user"]["is_email_verified"] is False
    # NO dev_verification_token in response
    assert "dev_verification_token" not in data
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]


def test_2_duplicate_email_rejected():
    _register(email="dup@gmail.com")
    res = _register(name="Alice Two", email="dup@gmail.com")
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


def test_3_invalid_email_rejected():
    res = client.post("/api/auth/register", json={
        "name": "Bad Email", "email": "not-an-email", "password": "password123"
    })
    assert res.status_code == 422


def test_3b_non_gmail_rejected(monkeypatch):
    """Non-Gmail addresses must be rejected when Gmail-only mode is enabled."""
    from backend.app.config import settings
    monkeypatch.setattr(settings, "GMAIL_ONLY", True)
    res = client.post("/api/auth/register", json={
        "name": "Not Gmail", "email": "user@yahoo.com", "password": "password123"
    })
    assert res.status_code == 400
    assert "Only Gmail addresses" in res.json()["detail"]



def test_4_weak_password_rejected():
    res = client.post("/api/auth/register", json={
        "name": "Weak Pass", "email": "weak@gmail.com", "password": "123"
    })
    assert res.status_code == 422


def test_5_password_stored_only_as_hash():
    res = _register(email="hash@gmail.com", password="mysecretpassword1")
    uid = res.json()["user"]["id"]
    stored_user = test_db.users[uid]
    assert stored_user["password_hash"] != "mysecretpassword1"
    assert verify_password("mysecretpassword1", stored_user["password_hash"])


# ─── Verification Tests ───────────────────────────────────────────────────────

def test_6_verification_token_stored_as_hash():
    res = _register(email="tokencheck@gmail.com")
    uid = res.json()["user"]["id"]
    # A token doc must exist for this user
    doc = _get_token_doc_for_user(uid)
    assert doc is not None
    # The stored field must be a 64-char SHA-256 hash, not plaintext token
    assert "token_hash" in doc
    assert len(doc["token_hash"]) == 64



def test_7_valid_email_verification():
    """
    Simulate a user clicking the link: we extract the hash from the mock DB
    and reverse-engineer the correct lookup, then call the endpoint with a
    known token whose hash we put directly into the mock store.
    """
    import secrets
    plain_token = secrets.token_urlsafe(32)
    t_hash = hash_token(plain_token)
    now = datetime.now(timezone.utc)
    uid = str(ObjectId())

    # Insert a user
    test_db.users[uid] = {
        "_id": ObjectId(uid),
        "name": "Verify Me",
        "email": "verifyme@gmail.com",
        "password_hash": hash_password("password123"),
        "is_active": True,
        "is_email_verified": False,
        "last_verification_sent_at": None,
        "created_at": now,
        "updated_at": now,
    }
    # Insert a token doc by hash
    test_db.email_verification_tokens[t_hash] = {
        "_id": str(ObjectId()),
        "token_hash": t_hash,
        "user_id": uid,
        "email": "verifyme@gmail.com",
        "used": False,
        "expires_at": now + timedelta(hours=1),
        "created_at": now,
    }

    res = client.post("/api/auth/verify-email", json={"token": plain_token})
    assert res.status_code == 200
    assert "verified" in res.json()["message"].lower()
    assert test_db.users[uid]["is_email_verified"] is True


def test_8_invalid_verification_fails():
    res = client.post("/api/auth/verify-email", json={"token": "invalid-token-1234567890"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid or expired verification link."


def test_9_expired_verification_fails():
    import secrets
    plain_token = secrets.token_urlsafe(32)
    t_hash = hash_token(plain_token)
    now = datetime.now(timezone.utc)

    test_db.email_verification_tokens[t_hash] = {
        "_id": str(ObjectId()),
        "token_hash": t_hash,
        "user_id": str(ObjectId()),
        "email": "expired@gmail.com",
        "used": False,
        "expires_at": now - timedelta(hours=1),
        "created_at": now,
    }
    res = client.post("/api/auth/verify-email", json={"token": plain_token})
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()


def test_10_used_verification_token_cannot_be_reused():
    import secrets
    plain_token = secrets.token_urlsafe(32)
    t_hash = hash_token(plain_token)
    now = datetime.now(timezone.utc)
    uid = str(ObjectId())

    test_db.users[uid] = {
        "_id": ObjectId(uid),
        "name": "Reuse Test",
        "email": "reuse@gmail.com",
        "password_hash": hash_password("password123"),
        "is_active": True,
        "is_email_verified": False,
        "last_verification_sent_at": None,
        "created_at": now,
        "updated_at": now,
    }
    test_db.email_verification_tokens[t_hash] = {
        "_id": str(ObjectId()),
        "token_hash": t_hash,
        "user_id": uid,
        "email": "reuse@gmail.com",
        "used": False,
        "expires_at": now + timedelta(hours=1),
        "created_at": now,
    }

    # First use — success
    r1 = client.post("/api/auth/verify-email", json={"token": plain_token})
    assert r1.status_code == 200

    # Second use — already verified
    r2 = client.post("/api/auth/verify-email", json={"token": plain_token})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "Email is already verified."


# ─── Resend Verification Tests ────────────────────────────────────────────────

def test_resend_verification_sends_new_token():
    """After registration, resend-verification generates a new token (via mocked email)."""
    reg = _register(email="resend@gmail.com")
    uid = reg.json()["user"]["id"]

    # Mark last_verification_sent_at far enough in the past to bypass cooldown
    test_db.users[uid]["last_verification_sent_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=120)
    )

    login = client.post("/api/auth/login", json={"email": "resend@gmail.com", "password": "securepass123"})
    cookies = login.cookies

    res = client.post("/api/auth/resend-verification", cookies=cookies)
    assert res.status_code == 200
    assert "sent" in res.json()["message"].lower()
    # NO dev_verification_token in response
    assert "dev_verification_token" not in res.json()


def test_resend_rate_limiting():
    """Cannot resend more than once within the cooldown window."""
    reg = _register(email="ratelimit@gmail.com")
    uid = reg.json()["user"]["id"]
    # Simulate that an email was just sent (within cooldown)
    test_db.users[uid]["last_verification_sent_at"] = datetime.now(timezone.utc)

    login = client.post("/api/auth/login", json={"email": "ratelimit@gmail.com", "password": "securepass123"})
    res = client.post("/api/auth/resend-verification", cookies=login.cookies)
    assert res.status_code == 429
    assert "wait" in res.json()["detail"].lower()


def test_resend_already_verified_fails():
    """Resend is blocked when email is already verified."""
    reg = _register(email="alreadyv@gmail.com")
    uid = reg.json()["user"]["id"]
    test_db.users[uid]["is_email_verified"] = True

    login = client.post("/api/auth/login", json={"email": "alreadyv@gmail.com", "password": "securepass123"})
    res = client.post("/api/auth/resend-verification", cookies=login.cookies)
    assert res.status_code == 400
    assert res.json()["detail"] == "Email is already verified."


def test_verification_error_messages():
    # Invalid token
    res_inv = client.post("/api/auth/verify-email", json={"token": "non-existent-token-xyz"})
    assert res_inv.status_code == 400
    assert res_inv.json()["detail"] == "Invalid or expired verification link."

    # Expired token
    import secrets
    plain = secrets.token_urlsafe(32)
    t_hash = hash_token(plain)
    now = datetime.now(timezone.utc)
    test_db.email_verification_tokens[t_hash] = {
        "_id": str(ObjectId()),
        "token_hash": t_hash,
        "user_id": str(ObjectId()),
        "email": "exp2@gmail.com",
        "used": False,
        "expires_at": now - timedelta(hours=2),
        "created_at": now,
    }
    res_exp = client.post("/api/auth/verify-email", json={"token": plain})
    assert res_exp.status_code == 400
    assert res_exp.json()["detail"] == "Verification link has expired. Please request a new verification email."


# ─── Login Tests ──────────────────────────────────────────────────────────────

def test_11_15_16_correct_credentials_login_and_cookies():
    _register(email="login@gmail.com")
    res = client.post("/api/auth/login", json={"email": "login@gmail.com", "password": "securepass123"})
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "login@gmail.com"
    assert "access_token" in res.cookies
    assert "refresh_token" in res.cookies


def test_12_incorrect_password_fails():
    _register(email="wrongpass@gmail.com")
    res = client.post("/api/auth/login", json={"email": "wrongpass@gmail.com", "password": "wrongpassword"})
    assert res.status_code == 401


def test_13_unknown_email_fails():
    res = client.post("/api/auth/login", json={"email": "nonexistent@gmail.com", "password": "password123"})
    assert res.status_code == 401


def test_14_inactive_account_login_fails():
    reg = _register(email="inactive@gmail.com")
    uid = reg.json()["user"]["id"]
    test_db.users[uid]["is_active"] = False
    res = client.post("/api/auth/login", json={"email": "inactive@gmail.com", "password": "securepass123"})
    assert res.status_code == 403


# ─── /me Tests ───────────────────────────────────────────────────────────────

def test_17_get_me_with_valid_auth():
    _register(name="Me User", email="me@gmail.com")
    client.post("/api/auth/login", json={"email": "me@gmail.com", "password": "securepass123"})
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Me User"
    assert data["email"] == "me@gmail.com"


def test_18_get_me_unauthenticated_fails():
    client.cookies.clear()
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_19_invalid_access_token_fails():
    client.cookies.set("access_token", "invalid.jwt.token")
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_20_expired_access_token_fails():
    expired_token = create_access_token({"sub": str(ObjectId())}, expires_delta=timedelta(seconds=-10))
    client.cookies.set("access_token", expired_token)
    res = client.get("/api/auth/me")
    assert res.status_code == 401


# ─── Token Refresh Tests ──────────────────────────────────────────────────────

def test_21_22_23_refresh_token_rotation():
    _register(email="refresh@gmail.com")
    login_res = client.post("/api/auth/login", json={"email": "refresh@gmail.com", "password": "securepass123"})
    old_refresh = login_res.cookies["refresh_token"]

    res = client.post("/api/auth/refresh")
    assert res.status_code == 200
    new_refresh = res.cookies["refresh_token"]
    assert new_refresh != old_refresh

    # Reusing old (revoked) token should fail
    client.cookies.clear()
    client.cookies.set("refresh_token", old_refresh)
    res_reuse = client.post("/api/auth/refresh")
    assert res_reuse.status_code == 401


def test_24_revoked_refresh_token_fails():
    _register(email="revoke@gmail.com")
    client.post("/api/auth/login", json={"email": "revoke@gmail.com", "password": "securepass123"})
    for sess in test_db.auth_sessions.values():
        sess["is_revoked"] = True
    res = client.post("/api/auth/refresh")
    assert res.status_code == 401


# ─── Logout Tests ─────────────────────────────────────────────────────────────

def test_26_27_28_logout_clears_cookies_and_revokes_session():
    _register(email="logout@gmail.com")
    client.post("/api/auth/login", json={"email": "logout@gmail.com", "password": "securepass123"})
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    for sess in test_db.auth_sessions.values():
        assert sess["is_revoked"] is True


# ─── Forgot & Reset Password Tests ───────────────────────────────────────────

def test_30_31_forgot_password_safe_response():
    _register(email="forgot@gmail.com")

    # Known email — should succeed and NOT expose a dev_reset_token
    res_exist = client.post("/api/auth/forgot-password", json={"email": "forgot@gmail.com"})
    assert res_exist.status_code == 200
    assert "dev_reset_token" not in res_exist.json()

    # Unknown email — same safe message
    res_unknown = client.post("/api/auth/forgot-password", json={"email": "unknown@gmail.com"})
    assert res_unknown.status_code == 200
    assert res_unknown.json()["message"] == res_exist.json()["message"]


def test_32_35_36_valid_reset_password_and_login():
    """Reset password using a token we construct directly in the mock DB."""
    import secrets

    _register(name="Reset User", email="reset@gmail.com", password="oldpassword123")

    # Find the user
    uid = None
    for k, u in test_db.users.items():
        if u["email"] == "reset@gmail.com":
            uid = k
            break
    assert uid is not None

    # Craft a reset token and inject hash into mock DB
    plain_token = secrets.token_urlsafe(32)
    t_hash = hash_token(plain_token)
    now = datetime.now(timezone.utc)
    test_db.password_reset_tokens[t_hash] = {
        "_id": str(ObjectId()),
        "token_hash": t_hash,
        "user_id": uid,
        "used": False,
        "expires_at": now + timedelta(minutes=30),
        "created_at": now,
    }

    res_reset = client.post("/api/auth/reset-password", json={
        "token": plain_token, "new_password": "newpassword123"
    })
    assert res_reset.status_code == 200

    # Old password fails
    res_old = client.post("/api/auth/login", json={"email": "reset@gmail.com", "password": "oldpassword123"})
    assert res_old.status_code == 401

    # New password succeeds
    res_new = client.post("/api/auth/login", json={"email": "reset@gmail.com", "password": "newpassword123"})
    assert res_new.status_code == 200


# ─── Security Tests ───────────────────────────────────────────────────────────

def test_37_38_password_hash_never_exposed_in_api():
    reg = _register(email="sec@gmail.com")
    client.post("/api/auth/login", json={"email": "sec@gmail.com", "password": "securepass123"})
    me = client.get("/api/auth/me")

    reg_json = str(reg.json())
    me_json = str(me.json())
    assert "password" not in reg_json
    assert "password_hash" not in reg_json
    assert "password" not in me_json
    assert "password_hash" not in me_json


def test_no_dev_token_in_any_response():
    """Ensures the dev backdoor tokens are completely gone from all API responses."""
    reg = _register(email="nodevtoken@gmail.com")
    assert "dev_verification_token" not in reg.json()
    assert "dev_reset_token" not in reg.json()

    fp = client.post("/api/auth/forgot-password", json={"email": "nodevtoken@gmail.com"})
    assert "dev_reset_token" not in fp.json()


def test_email_only_verified_after_link_click():
    """
    Core invariant: is_email_verified must be False immediately after register.
    It can only become True after a valid verify-email call.
    """
    reg = _register(email="invariant@gmail.com")
    uid = reg.json()["user"]["id"]
    assert test_db.users[uid]["is_email_verified"] is False

    # No magic — must still be False without actually clicking the link
    login = client.post("/api/auth/login", json={"email": "invariant@gmail.com", "password": "securepass123"})
    me = client.get("/api/auth/me", cookies=login.cookies)
    assert me.json()["is_email_verified"] is False


# ─── Verification Flow Test Cases (A through H) ──────────────────────────────

def test_case_a_correct_smtp_configuration(monkeypatch):
    """
    Case A: Correct SMTP configuration.
    Verification email is actually sent, message confirms sent, account remains is_email_verified=False.
    We monkeypatch both the email sender AND is_smtp_configured so the register endpoint
    returns the 'Verification email sent' message (not the dev_console fallback).
    """
    sent_emails = []
    def mock_send(to_email, name, token):
        sent_emails.append({"to": to_email, "name": name, "token": token})
        return True, None

    monkeypatch.setattr("backend.app.api.auth.send_verification_email", mock_send)
    # Simulate SMTP being configured so we get the real success message
    from backend.app.config import settings as _settings
    monkeypatch.setattr(type(_settings), "is_smtp_configured", property(lambda self: True))

    res = client.post("/api/auth/register", json={"name": "Alice", "email": "alice_case_a@gmail.com", "password": "password123"})
    assert res.status_code == 201
    data = res.json()
    assert "Verification email sent" in data["message"]
    assert data["user"]["is_email_verified"] is False
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "alice_case_a@gmail.com"


def test_case_b_wrong_smtp_credentials(monkeypatch):
    """
    Case B: Wrong SMTP credentials.
    Friendly error 'Unable to send verification email. Please try again later.',
    account created but remains unverified (is_email_verified=False).
    No credentials or stack traces leaked.
    """
    monkeypatch.setattr(
        "backend.app.api.auth.send_verification_email",
        lambda to, name, token: (False, "Unable to send verification email. Please try again later.")
    )
    res = client.post("/api/auth/register", json={"name": "Bob", "email": "bob_case_b@gmail.com", "password": "password123"})
    assert res.status_code == 201
    data = res.json()
    assert "Unable to send verification email" in data["message"]
    assert data["user"]["is_email_verified"] is False
    assert "password" not in data["message"].lower()
    assert "smtp" not in data["message"].lower()


def test_case_c_missing_smtp_configuration(monkeypatch):
    """
    Case C: Missing SMTP configuration.
    Friendly configuration error: 'Verification email could not be sent. Email service is not configured.',
    account created but remains unverified (is_email_verified=False).
    """
    monkeypatch.setattr(
        "backend.app.api.auth.send_verification_email",
        lambda to, name, token: (False, "Verification email could not be sent. Email service is not configured.")
    )
    res = client.post("/api/auth/register", json={"name": "Charlie", "email": "charlie_case_c@gmail.com", "password": "password123"})
    assert res.status_code == 201
    data = res.json()
    assert "Email service is not configured" in data["message"]
    assert data["user"]["is_email_verified"] is False


def test_case_d_user_receives_email_and_clicks_verification_link(monkeypatch):
    """
    Case D: User receives email and clicks verification link.
    Account becomes verified (is_email_verified=True).
    """
    captured_token = {}
    def mock_send(to_email, name, token):
        captured_token["token"] = token
        return True, None

    monkeypatch.setattr("backend.app.api.auth.send_verification_email", mock_send)
    reg = client.post("/api/auth/register", json={"name": "Dana", "email": "dana_case_d@gmail.com", "password": "password123"})
    assert reg.status_code == 201
    uid = reg.json()["user"]["id"]
    assert test_db.users[uid]["is_email_verified"] is False

    # User clicks link with token
    token = captured_token["token"]
    verify_res = client.post("/api/auth/verify-email", json={"token": token})
    assert verify_res.status_code == 200
    assert "verified successfully" in verify_res.json()["message"].lower()
    assert test_db.users[uid]["is_email_verified"] is True


def test_case_e_fake_or_nonexistent_email_stays_unverified(monkeypatch):
    """
    Case E: User enters a fake/non-existent Gmail address.
    Account must NOT automatically become verified.
    """
    monkeypatch.setattr(
        "backend.app.api.auth.send_verification_email",
        lambda to, name, token: (False, "The address was rejected by the mail server. Please check that the address is correct.")
    )
    reg = client.post("/api/auth/register", json={"name": "Fake", "email": "fake_nonexistent_addr_12345@gmail.com", "password": "password123"})
    assert reg.status_code == 201
    uid = reg.json()["user"]["id"]
    assert test_db.users[uid]["is_email_verified"] is False


def test_case_f_user_clicks_verify_email_but_not_link(monkeypatch):
    """
    Case F: User clicks Verify Email (requests verification) but does not click the email link.
    Account remains unverified (is_email_verified=False).
    """
    reg = _register(email="user_case_f@gmail.com")
    uid = reg.json()["user"]["id"]
    assert test_db.users[uid]["is_email_verified"] is False

    # User logs in and visits dashboard/profile
    login = client.post("/api/auth/login", json={"email": "user_case_f@gmail.com", "password": "securepass123"})
    me = client.get("/api/auth/me", cookies=login.cookies)
    assert me.status_code == 200
    assert me.json()["is_email_verified"] is False


def test_case_g_reuse_old_verification_link(monkeypatch):
    """
    Case G: User reuses an old / already-used verification link.
    Reject it (HTTP 400).
    """
    captured_token = {}
    monkeypatch.setattr(
        "backend.app.api.auth.send_verification_email",
        lambda to, name, token: captured_token.update({"token": token}) or (True, None)
    )
    reg = client.post("/api/auth/register", json={"name": "Grace", "email": "grace_case_g@gmail.com", "password": "password123"})
    assert reg.status_code == 201
    token = captured_token["token"]

    # First verification attempt succeeds
    v1 = client.post("/api/auth/verify-email", json={"token": token})
    assert v1.status_code == 200

    # Second attempt with same token must be rejected
    v2 = client.post("/api/auth/verify-email", json={"token": token})
    assert v2.status_code == 400
    assert "already" in v2.json()["detail"].lower()


def test_case_h_expired_token_rejected_and_resend_allowed(monkeypatch):
    """
    Case H: Verification token expires.
    Reject it (HTTP 400), and allow requesting a new token via resend.
    """
    captured_token = {}
    monkeypatch.setattr(
        "backend.app.api.auth.send_verification_email",
        lambda to, name, token: captured_token.update({"token": token}) or (True, None)
    )
    reg = client.post("/api/auth/register", json={"name": "Hannah", "email": "hannah_case_h@gmail.com", "password": "password123"})
    assert reg.status_code == 201
    uid = reg.json()["user"]["id"]
    token = captured_token["token"]

    # Expire the token in DB
    tok_doc = _get_token_doc_for_user(uid)
    tok_doc["expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=5)

    # Attempt verification with expired token -> must be rejected
    v_expired = client.post("/api/auth/verify-email", json={"token": token})
    assert v_expired.status_code == 400
    assert "expired" in v_expired.json()["detail"].lower()
    assert test_db.users[uid]["is_email_verified"] is False

    # Log in to resend
    login = client.post("/api/auth/login", json={"email": "hannah_case_h@gmail.com", "password": "password123"})

    # Fast-forward cooldown
    test_db.users[uid]["last_verification_sent_at"] = datetime.now(timezone.utc) - timedelta(seconds=70)

    resend = client.post("/api/auth/resend-verification", cookies=login.cookies)
    assert resend.status_code == 200
    new_token = captured_token["token"]
    assert new_token != token

    # Verify with fresh token -> succeeds
    v_fresh = client.post("/api/auth/verify-email", json={"token": new_token})
    assert v_fresh.status_code == 200
    assert test_db.users[uid]["is_email_verified"] is True


def test_smtp_status_endpoint():
    """Verify GET /api/auth/smtp-status returns public status without credentials."""
    res = client.get("/api/auth/smtp-status")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert "host" in data
    assert "port" in data
    assert "password" not in data
    assert "smtp_password" not in data

