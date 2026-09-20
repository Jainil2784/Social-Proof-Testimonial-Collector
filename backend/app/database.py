# MongoDB is the primary database layer (configured in backend.app.db.mongodb)
from backend.app.db.mongodb import db_manager, get_database, get_collection

__all__ = ["db_manager", "get_database", "get_collection"]
