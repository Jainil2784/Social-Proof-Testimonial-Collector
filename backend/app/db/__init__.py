from backend.app.db.indexes import create_mongo_indexes
from backend.app.db.mongodb import (
    close_mongo_connection,
    connect_to_mongo,
    db_manager,
    get_collection,
    get_database,
    get_spaces_collection,
    get_testimonials_collection,
    get_users_collection,
)

__all__ = [
    "connect_to_mongo",
    "close_mongo_connection",
    "get_database",
    "get_collection",
    "get_users_collection",
    "get_spaces_collection",
    "get_testimonials_collection",
    "create_mongo_indexes",
    "db_manager",
]
