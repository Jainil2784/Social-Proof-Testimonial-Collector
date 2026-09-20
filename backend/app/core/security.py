import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
import bcrypt
import jwt
from backend.app.config import settings


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against bcrypt hashed password."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def hash_token(token: str) -> str:
    """Create SHA-256 hash of a token for secure storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived JWT access token (15 mins default)."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=15))
    to_encode.update({
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> Tuple[str, str, datetime]:
    """Create a long-lived JWT refresh token (7 days default). Returns (token_str, token_id, expires_at)."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=7))
    token_id = str(uuid.uuid4())
    to_encode.update({
        "type": "refresh",
        "jti": token_id,
        "iat": now,
        "exp": expire
    })
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, token_id, expire


def decode_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify JWT token. Returns payload dict or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
