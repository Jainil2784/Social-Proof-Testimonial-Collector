#!/usr/bin/env python3
"""
Migration script: Reset all users to is_email_verified = false.

Run this ONCE after deploying the new real email-verification system to fix
accounts that were incorrectly auto-verified by the old dummy implementation.

Passwords and all other user data are UNTOUCHED.

Usage:
    cd "f:\\Com Bot Project"
    .\\venv\\Scripts\\python.exe backend/scripts/reset_unverified_accounts.py

The script will print how many accounts were updated.
"""

import asyncio
import sys
import os

# Make sure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from datetime import datetime, timezone
from pymongo import AsyncMongoClient

from backend.app.config import settings


async def main():
    print(f"Connecting to MongoDB: {settings.MONGODB_URL[:40]}...")
    client = AsyncMongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=10_000)
    db = client[settings.MONGODB_DATABASE_NAME]

    try:
        await client.admin.command("ping")
        print("✓ Connected to MongoDB.")
    except Exception as e:
        print(f"✗ Could not connect to MongoDB: {e}")
        await client.close()
        sys.exit(1)

    users_coll = db["users"]
    tokens_coll = db["email_verification_tokens"]

    # Count how many are currently marked verified
    total = await users_coll.count_documents({})
    already_verified = await users_coll.count_documents({"is_email_verified": True})
    print(f"\nTotal user accounts: {total}")
    print(f"Currently marked as verified: {already_verified}")

    if already_verified == 0:
        print("\n✓ No accounts to migrate. All good.")
        await client.close()
        return

    confirm = input(
        f"\n⚠  This will reset {already_verified} account(s) to is_email_verified=False.\n"
        "   Passwords and all other data are UNTOUCHED.\n"
        "   Type 'yes' to continue: "
    ).strip().lower()

    if confirm != "yes":
        print("Aborted — no changes made.")
        await client.close()
        return

    now = datetime.now(timezone.utc)

    # Reset verification status on all users
    result = await users_coll.update_many(
        {},
        {"$set": {
            "is_email_verified": False,
            "last_verification_sent_at": None,
            "updated_at": now,
        }}
    )
    print(f"\n✓ Reset {result.modified_count} user account(s) to is_email_verified=False.")

    # Also mark all existing verification tokens as invalidated so they can't be reused
    tok_result = await tokens_coll.update_many(
        {"used": False},
        {"$set": {"used": True, "invalidated_at": now, "reason": "migration_reset"}}
    )
    print(f"✓ Invalidated {tok_result.modified_count} pending verification token(s).")

    print("\n✅ Migration complete. Users must re-verify their email addresses.")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
