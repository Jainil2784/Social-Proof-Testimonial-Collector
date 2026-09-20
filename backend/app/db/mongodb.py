import logging
from typing import Optional
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError
from backend.app.config import settings

logger = logging.getLogger(__name__)


class MongoDBManager:
    client: Optional[AsyncMongoClient] = None
    db: Optional[AsyncDatabase] = None


db_manager = MongoDBManager()


async def connect_to_mongo(url: Optional[str] = None, db_name: Optional[str] = None):
    """
    Connect to MongoDB using PyMongo AsyncMongoClient, ping the server, and store references.
    """
    mongodb_url = url or settings.MONGODB_URL
    database_name = db_name or settings.MONGODB_DATABASE_NAME

    logger.info(f"Connecting to MongoDB at {mongodb_url}...")
    db_manager.client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
    db_manager.db = db_manager.client[database_name]

    try:
        await db_manager.client.admin.command("ping")
        logger.info("MongoDB ping succeeded!")
    except Exception as e:
        logger.warning(f"MongoDB ping warning: {e}")


async def close_mongo_connection():
    """
    Cleanly close the MongoDB AsyncMongoClient.
    """
    if db_manager.client:
        logger.info("Closing MongoDB connection...")
        await db_manager.client.close()
        db_manager.client = None
        db_manager.db = None


def get_database() -> AsyncDatabase:
    """
    Helper function to return current MongoDB database instance.
    Auto-initializes client reference if not yet created.
    """
    if db_manager.db is None:
        mongodb_url = settings.MONGODB_URL
        database_name = settings.MONGODB_DATABASE_NAME
        db_manager.client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
        db_manager.db = db_manager.client[database_name]
    return db_manager.db


def get_collection(collection_name: str):
    """
    Helper function to get a specific MongoDB collection.
    """
    db = get_database()
    return db[collection_name]


def get_users_collection():
    return get_collection("users")


def get_spaces_collection():
    return get_collection("spaces")


def get_testimonials_collection():
    return get_collection("testimonials")


def get_auth_sessions_collection():
    return get_collection("auth_sessions")


def get_verification_tokens_collection():
    return get_collection("email_verification_tokens")


def get_password_reset_tokens_collection():
    return get_collection("password_reset_tokens")
