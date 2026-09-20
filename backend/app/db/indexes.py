import logging
from pymongo import ASCENDING, DESCENDING
from backend.app.db.mongodb import get_database

logger = logging.getLogger(__name__)


async def create_mongo_indexes():
    """
    Create MongoDB indexes for all collections.
    """
    db = get_database()

    # 1. users indexes
    await db.users.create_index([("email", ASCENDING)], unique=True)
    # for resend rate-limiting queries
    await db.users.create_index([("last_verification_sent_at", ASCENDING)])

    # 2. spaces indexes
    await db.spaces.create_index([("slug", ASCENDING)], unique=True)
    await db.spaces.create_index([("owner_id", ASCENDING)])

    # 3. testimonials indexes
    await db.testimonials.create_index([("space_id", ASCENDING)])
    await db.testimonials.create_index([("status", ASCENDING)])
    await db.testimonials.create_index([("rating", ASCENDING)])
    await db.testimonials.create_index([("is_featured", ASCENDING)])
    await db.testimonials.create_index([("created_at", DESCENDING)])
    await db.testimonials.create_index([
        ("space_id", ASCENDING),
        ("status", ASCENDING),
        ("created_at", DESCENDING)
    ])

    # 4. auth_sessions indexes
    await db.auth_sessions.create_index([("token_id", ASCENDING)], unique=True)
    await db.auth_sessions.create_index([("user_id", ASCENDING)])
    await db.auth_sessions.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)

    # 5. email_verification_tokens — stored by hash, not plaintext
    await db.email_verification_tokens.create_index([("token_hash", ASCENDING)], unique=True, sparse=True)
    await db.email_verification_tokens.create_index([("user_id", ASCENDING)])
    await db.email_verification_tokens.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)

    # 6. password_reset_tokens — stored by hash, not plaintext
    await db.password_reset_tokens.create_index([("token_hash", ASCENDING)], unique=True, sparse=True)
    await db.password_reset_tokens.create_index([("user_id", ASCENDING)])
    await db.password_reset_tokens.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)


    logger.info("MongoDB indexes created successfully.")
