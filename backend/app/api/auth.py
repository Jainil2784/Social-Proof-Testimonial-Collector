from datetime import datetime, timedelta, timezone
import logging
import secrets
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

logger = logging.getLogger(__name__)


from backend.app.core.auth_dependency import get_current_user
from backend.app.core.email import send_verification_email, send_password_reset_email
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    hash_password,
    hash_token,
    verify_password,
)
from backend.app.config import settings
from backend.app.db.mongodb import (
    get_auth_sessions_collection,
    get_password_reset_tokens_collection,
    get_users_collection,
    get_verification_tokens_collection,
)
from backend.app.schemas.auth import (
    AuthUserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationResponse,
    ResetPasswordRequest,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ─── Register ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_owner(req: RegisterRequest):
    """
    Register a new Business Owner account.

    After registration a verification email is dispatched to the supplied Gmail
    address.  is_email_verified stays False until the user clicks the link.
    The token is NEVER returned to the frontend.
    """
    email_clean = req.email.lower().strip()
    users_coll = get_users_collection()

    if settings.GMAIL_ONLY and not email_clean.endswith("@gmail.com"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Gmail addresses (@gmail.com) are supported at this time."
        )

    existing_user = await users_coll.find_one({"email": email_clean})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists."
        )

    now = datetime.now(timezone.utc)
    user_doc = {
        "name": req.name.strip(),
        "email": email_clean,
        "password_hash": hash_password(req.password),
        "is_active": True,
        "is_email_verified": False,
        "last_verification_sent_at": None,   # used for resend rate-limiting
        "created_at": now,
        "updated_at": now,
    }

    result = await users_coll.insert_one(user_doc)
    user_id_str = str(result.inserted_id)

    # Generate a cryptographically secure token and store its HASH.
    # The plain token goes into the email link; we never return it to the API caller.
    verification_token = secrets.token_urlsafe(32)
    token_hash = hash_token(verification_token)

    verification_tokens_coll = get_verification_tokens_collection()
    await verification_tokens_coll.insert_one({
        "token_hash": token_hash,
        "token": token_hash,
        "user_id": user_id_str,
        "email": email_clean,
        "used": False,
        "expires_at": now + timedelta(minutes=settings.VERIFICATION_TOKEN_EXPIRE_MINUTES),
        "created_at": now,
    })


    # Update last_verification_sent_at on the user (for rate limiting)
    await users_coll.update_one(
        {"_id": result.inserted_id},
        {"$set": {"last_verification_sent_at": now}},
    )

    # Send the actual verification email (or print to console if SMTP not configured)
    ok, err = send_verification_email(email_clean, req.name.strip(), verification_token)
    if ok:
        if settings.is_smtp_configured:
            message = "Verification email sent. Please check your Gmail inbox and click the verification link."
        else:
            # Dev console mode — link was printed to the uvicorn terminal
            message = "dev_console"
    else:
        if err and "not configured" in err.lower():
            message = "Verification email could not be sent. Email service is not configured."
        elif err and any(w in err.lower() for w in ["refused", "recipient", "invalid", "rejected"]):
            message = "Unable to send verification email. Please enter a valid Gmail address."
        else:
            message = "Unable to send verification email. Please try again later."

    user_response = AuthUserResponse(
        id=user_id_str,
        name=user_doc["name"],
        email=user_doc["email"],
        is_email_verified=False,
        created_at=now,
        updated_at=now,
    )

    return RegisterResponse(
        message=message,
        user=user_response,
    )



# ─── Verify Email ────────────────────────────────────────────────────────────

async def process_email_verification(token: str) -> Tuple[str, str]:
    """
    Process an email verification token against MongoDB.
    Returns (status_key, message) where status_key is one of:
      - 'success': verified and updated is_email_verified=True
      - 'already_verified': user account is already verified
      - 'already_used': token has already been consumed
      - 'expired': token has expired
      - 'invalid': token hash not found in database or user not found
      - 'missing': token is empty or None
      - 'error': database or unexpected error
    """
    if not token or not str(token).strip():
        return "missing", "No verification token was provided."

    try:
        token_hash = hash_token(str(token).strip())
        verification_tokens_coll = get_verification_tokens_collection()
        users_coll = get_users_collection()

        token_doc = await verification_tokens_coll.find_one({"token_hash": token_hash})
        if not token_doc:
            token_doc = await verification_tokens_coll.find_one({"token": token_hash})

        if not token_doc:
            return "invalid", "This verification link is invalid or no longer available."

        user_id_str = token_doc.get("user_id")
        user = await users_coll.find_one({"_id": ObjectId(user_id_str)}) if user_id_str else None

        if token_doc.get("used", False):
            if user and user.get("is_email_verified", False):
                return "already_verified", "Your email address has already been verified."
            return "already_used", "This verification link has already been used. Please request a new one."

        expires_at = token_doc.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at and expires_at < datetime.now(timezone.utc):
            return "expired", "This verification link has expired. Please request a new verification email."

        if not user:
            return "invalid", "Associated user account not found."

        if user.get("is_email_verified", False):
            await verification_tokens_coll.update_one(
                {"_id": token_doc["_id"]},
                {"$set": {"used": True}},
            )
            return "already_verified", "Your email address has already been verified."

        # All checks passed — mark account verified in database
        now = datetime.now(timezone.utc)
        await users_coll.update_one(
            {"_id": ObjectId(user_id_str)},
            {"$set": {"is_email_verified": True, "updated_at": now}},
        )
        await verification_tokens_coll.update_one(
            {"_id": token_doc["_id"]},
            {"$set": {"used": True, "verified_at": now}},
        )
        return "success", "Your email address has been successfully verified."

    except Exception as exc:
        logger.error(f"Error during email verification: {exc}")
        return "error", "An unexpected error occurred while verifying your email."


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(req: VerifyEmailRequest):
    """
    Verify email address using the token from the verification link (POST API).
    Returns MessageResponse on success or raises HTTPException on error.
    """
    status_key, message = await process_email_verification(req.token)

    if status_key == "success":
        return MessageResponse(message="Email address verified successfully.")
    elif status_key == "already_verified":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified."
        )
    elif status_key == "expired":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link has expired. Please request a new verification email."
        )
    elif status_key == "already_used":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has already been used. Please request a new one."
        )
    elif status_key in ("invalid", "missing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link."
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )


# ─── Resend Verification ─────────────────────────────────────────────────────

@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(current_user: dict = Depends(get_current_user)):
    """
    Re-send the verification email for the authenticated user.

    Rate-limited: at most one email per RESEND_COOLDOWN_SECONDS.
    The token is NEVER returned to the caller — it goes into the email only.
    """
    if current_user.get("is_email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified."
        )

    now = datetime.now(timezone.utc)
    cooldown = timedelta(seconds=settings.RESEND_COOLDOWN_SECONDS)

    last_sent = current_user.get("last_verification_sent_at")
    if last_sent:
        if isinstance(last_sent, datetime) and last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        elapsed = now - last_sent
        if elapsed < cooldown:
            remaining = int((cooldown - elapsed).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before requesting another verification email.",
                headers={"Retry-After": str(remaining)},
            )

    user_id_str = current_user["id"]
    email = current_user["email"]
    name = current_user["name"]

    # Invalidate all previous unused tokens for this user
    verification_tokens_coll = get_verification_tokens_collection()
    await verification_tokens_coll.update_many(
        {"user_id": user_id_str, "used": False},
        {"$set": {"used": True, "invalidated_at": now}},
    )

    # Generate a fresh secure token — store hash only
    new_token = secrets.token_urlsafe(32)
    token_hash = hash_token(new_token)

    await verification_tokens_coll.insert_one({
        "token_hash": token_hash,
        "token": token_hash,
        "user_id": user_id_str,
        "email": email,
        "used": False,
        "expires_at": now + timedelta(minutes=settings.VERIFICATION_TOKEN_EXPIRE_MINUTES),
        "created_at": now,
    })


    # Record the send time for rate-limiting future calls
    users_coll = get_users_collection()
    await users_coll.update_one(
        {"_id": ObjectId(user_id_str)},
        {"$set": {"last_verification_sent_at": now}},
    )

    # Actually send the email
    ok, err = send_verification_email(email, name, new_token)
    if not ok:
        if err and "not configured" in err.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verification email could not be sent. Email service is not configured.",
            )
        if err and any(w in err.lower() for w in ["refused", "recipient", "invalid", "rejected"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to send verification email. Please enter a valid Gmail address.",
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to send verification email. Please try again later.",
        )


    return MessageResponse(
        message=(
            f"Verification email sent to {email}. "
            "Please check your Gmail inbox and click the link within "
            f"{settings.VERIFICATION_TOKEN_EXPIRE_MINUTES} minutes."
        )
    )


# ─── Login ───────────────────────────────────────────────────────────────────

@router.post("/login")
async def login_owner(req: LoginRequest, request: Request, response: Response):
    """
    Authenticate owner credentials and set HTTP-only JWT cookies.
    Email verification is NOT required for login, but is surfaced via is_email_verified.
    """
    email_clean = req.email.lower().strip()
    users_coll = get_users_collection()

    user = await users_coll.find_one({"email": email_clean})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password."
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive."
        )

    user_id_str = str(user["_id"])
    access_token = create_access_token({"sub": user_id_str, "email": user["email"]})
    refresh_token, token_id, expires_at = create_refresh_token({"sub": user_id_str})

    now = datetime.now(timezone.utc)
    auth_sessions_coll = get_auth_sessions_collection()
    await auth_sessions_coll.insert_one({
        "token_id": token_id,
        "user_id": user_id_str,
        "token_hash": hash_token(refresh_token),
        "expires_at": expires_at,
        "is_revoked": False,
        "created_at": now,
        "user_agent": request.headers.get("User-Agent"),
    })

    response.set_cookie(key="access_token", value=access_token, httponly=True,
                        max_age=15 * 60, path="/", samesite="lax", secure=False)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True,
                        max_age=7 * 24 * 60 * 60, path="/", samesite="lax", secure=False)

    user_response = AuthUserResponse(
        id=user_id_str,
        name=user["name"],
        email=user["email"],
        is_email_verified=user.get("is_email_verified", False),
        created_at=user["created_at"],
        updated_at=user["updated_at"],
    )

    return {"message": "Login successful.", "user": user_response}


# ─── Refresh ─────────────────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    """
    Rotate access + refresh tokens using the HTTP-only refresh cookie.
    """
    token_str = request.cookies.get("refresh_token")
    if not token_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Refresh token cookie missing.")

    payload = decode_jwt_token(token_str)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired refresh token.")

    token_id = payload.get("jti")
    user_id_str = payload.get("sub")

    auth_sessions_coll = get_auth_sessions_collection()
    session_doc = await auth_sessions_coll.find_one({"token_id": token_id})

    if not session_doc or session_doc.get("is_revoked", False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Refresh token has been revoked or is invalid.")

    expires_at = session_doc.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Refresh token session has expired.")

    new_access_token = create_access_token({"sub": user_id_str})
    new_refresh_token, new_token_id, new_expires_at = create_refresh_token({"sub": user_id_str})

    now = datetime.now(timezone.utc)
    await auth_sessions_coll.update_one(
        {"_id": session_doc["_id"]},
        {"$set": {"is_revoked": True, "replaced_by": new_token_id, "revoked_at": now}},
    )
    await auth_sessions_coll.insert_one({
        "token_id": new_token_id,
        "user_id": user_id_str,
        "token_hash": hash_token(new_refresh_token),
        "expires_at": new_expires_at,
        "is_revoked": False,
        "created_at": now,
        "user_agent": request.headers.get("User-Agent"),
    })

    response.set_cookie(key="access_token", value=new_access_token, httponly=True,
                        max_age=15 * 60, path="/", samesite="lax", secure=False)
    response.set_cookie(key="refresh_token", value=new_refresh_token, httponly=True,
                        max_age=7 * 24 * 60 * 60, path="/", samesite="lax", secure=False)

    return MessageResponse(message="Tokens refreshed successfully.")


# ─── Me ──────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=AuthUserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Return authenticated owner profile.
    is_email_verified comes from the database — never from frontend state.
    """
    return AuthUserResponse(
        id=current_user["id"],
        name=current_user["name"],
        email=current_user["email"],
        is_email_verified=current_user.get("is_email_verified", False),
        created_at=current_user["created_at"],
        updated_at=current_user["updated_at"],
    )


# ─── Logout ──────────────────────────────────────────────────────────────────

@router.post("/logout", response_model=MessageResponse)
async def logout_owner(request: Request, response: Response):
    """
    Logout owner, revoke refresh session, and clear HTTP-only cookies.
    """
    token_str = request.cookies.get("refresh_token")
    if token_str:
        payload = decode_jwt_token(token_str)
        if payload and payload.get("jti"):
            auth_sessions_coll = get_auth_sessions_collection()
            await auth_sessions_coll.update_one(
                {"token_id": payload["jti"]},
                {"$set": {"is_revoked": True, "revoked_at": datetime.now(timezone.utc)}},
            )

    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")

    return MessageResponse(message="Logged out successfully.")


# ─── Forgot Password ─────────────────────────────────────────────────────────

@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(req: ForgotPasswordRequest):
    """
    Send a password-reset email to the registered address.
    The reset token is sent via email ONLY — never returned in the API response.
    Safe response for unknown addresses (no user enumeration).
    """
    email_clean = req.email.lower().strip()
    users_coll = get_users_collection()
    user = await users_coll.find_one({"email": email_clean})

    SAFE_MSG = (
        "If an account with that email address exists, password reset "
        "instructions have been sent to your inbox."
    )

    if not user:
        return ForgotPasswordResponse(message=SAFE_MSG)

    reset_token = secrets.token_urlsafe(32)
    token_hash = hash_token(reset_token)
    user_id_str = str(user["_id"])
    now = datetime.now(timezone.utc)

    reset_tokens_coll = get_password_reset_tokens_collection()
    # Invalidate previous unused reset tokens
    await reset_tokens_coll.update_many(
        {"user_id": user_id_str, "used": False},
        {"$set": {"used": True, "invalidated_at": now}},
    )
    await reset_tokens_coll.insert_one({
        "token_hash": token_hash,
        "token": token_hash,
        "user_id": user_id_str,
        "used": False,
        "expires_at": now + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
        "created_at": now,
    })

    ok, err = send_password_reset_email(email_clean, user["name"], reset_token)
    if not ok:
        logger.warning(f"Could not send password reset email: {err}")

    return ForgotPasswordResponse(message=SAFE_MSG)


# ─── Reset Password ──────────────────────────────────────────────────────────

@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(req: ResetPasswordRequest):
    """
    Reset owner password using the token from the reset email link.
    The backend validates the token before changing anything.
    """
    token_hash = hash_token(req.token)
    reset_tokens_coll = get_password_reset_tokens_collection()
    token_doc = await reset_tokens_coll.find_one({"token_hash": token_hash})
    if not token_doc:
        token_doc = await reset_tokens_coll.find_one({"token": token_hash})


    if not token_doc or token_doc.get("used", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already used password reset token."
        )

    expires_at = token_doc.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired."
        )

    user_id_str = token_doc.get("user_id")
    users_coll = get_users_collection()
    user = await users_coll.find_one({"_id": ObjectId(user_id_str)})

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated user account not found."
        )

    now = datetime.now(timezone.utc)
    await users_coll.update_one(
        {"_id": ObjectId(user_id_str)},
        {"$set": {"password_hash": hash_password(req.new_password), "updated_at": now}},
    )
    await reset_tokens_coll.update_one(
        {"_id": token_doc["_id"]},
        {"$set": {"used": True, "reset_at": now}},
    )

    # Revoke all active sessions
    auth_sessions_coll = get_auth_sessions_collection()
    await auth_sessions_coll.update_many(
        {"user_id": user_id_str, "is_revoked": False},
        {"$set": {"is_revoked": True, "revoked_at": now, "reason": "password_reset"}},
    )

    return MessageResponse(message="Password reset successfully. You can now log in with your new password.")


# ─── SMTP Status Diagnostic ──────────────────────────────────────────────────

@router.get("/smtp-status")
async def get_smtp_status():
    """
    Check if the SMTP email service is configured.
    Returns safe configuration status without exposing credentials.
    """
    return {
        "configured": settings.is_smtp_configured,
        "host": settings.SMTP_HOST,
        "port": settings.SMTP_PORT,
        "from_name": settings.SMTP_FROM_NAME,
        "gmail_only": settings.GMAIL_ONLY,
    }
