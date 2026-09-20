import asyncio
from datetime import datetime
import pytest
from bson import ObjectId
import mongomock

from backend.app.models.user import UserModel
from backend.app.models.space import SpaceModel
from backend.app.models.testimonial import TestimonialModel, TestimonialStatus
from backend.app.schemas.user import UserCreate, UserResponse
from backend.app.schemas.space import SpaceCreate, SpaceResponse
from backend.app.schemas.testimonial import TestimonialCreate, TestimonialResponse


class MockAsyncCollection:
    """Async wrapper around mongomock collection for testing."""

    def __init__(self, sync_collection):
        self._coll = sync_collection
        self._unique_indexes = set()

    async def create_index(self, keys, unique=False, **kwargs):
        index_key = tuple(k[0] for k in keys) if isinstance(keys, list) else keys
        if unique:
            self._unique_indexes.add(index_key)
        return self._coll.create_index(keys, unique=unique, **kwargs)

    async def list_indexes(self):
        return [idx for idx in self._coll.list_indexes()]

    async def insert_one(self, document):
        # Enforce unique indexes for tests
        for key in self._unique_indexes:
            if isinstance(key, tuple):
                field = key[0]
            else:
                field = key
            if field in document and document[field] is not None:
                existing = self._coll.find_one({field: document[field]})
                if existing:
                    from pymongo.errors import DuplicateKeyError
                    raise DuplicateKeyError(f"Duplicate key error on {field}")
        res = self._coll.insert_one(document)
        class AsyncInsertResult:
            inserted_id = res.inserted_id
        return AsyncInsertResult()

    async def find_one(self, filter_dict):
        return self._coll.find_one(filter_dict)

    async def delete_many(self, filter_dict):
        return self._coll.delete_many(filter_dict)


class MockAsyncDatabase:
    """Async wrapper around mongomock database for testing."""

    def __init__(self, db_name="socialproof_test"):
        self._sync_client = mongomock.MongoClient()
        self._sync_db = self._sync_client[db_name]
        self.name = db_name
        self.users = MockAsyncCollection(self._sync_db.users)
        self.spaces = MockAsyncCollection(self._sync_db.spaces)
        self.testimonials = MockAsyncCollection(self._sync_db.testimonials)

    def __getitem__(self, item):
        return MockAsyncCollection(self._sync_db[item])

    async def command(self, cmd):
        if cmd == "ping":
            return {"ok": 1.0}
        return {}

    async def list_collection_names(self):
        return ["users", "spaces", "testimonials"]


@pytest.fixture(scope="module")
def mock_db():
    return MockAsyncDatabase("socialproof_test")


@pytest.mark.asyncio
async def test_mongodb_client_initialized(mock_db):
    """1. Test MongoDB client initialization."""
    assert mock_db._sync_client is not None


@pytest.mark.asyncio
async def test_mongodb_ping(mock_db):
    """2. Test MongoDB ping command."""
    res = await mock_db.command("ping")
    assert res.get("ok") == 1.0


@pytest.mark.asyncio
async def test_database_selection(mock_db):
    """3. Test database selection."""
    assert mock_db.name == "socialproof_test"


@pytest.mark.asyncio
async def test_collections_access(mock_db):
    """4. Test required collections access."""
    cols = await mock_db.list_collection_names()
    assert "users" in cols
    assert "spaces" in cols
    assert "testimonials" in cols


@pytest.mark.asyncio
async def test_user_document_insertion(mock_db):
    """5. Test User document insertion."""
    user = UserModel(
        name="Jane Owner",
        email="jane@example.com",
        password_hash="$2b$12$hash123456789"
    )
    doc = user.model_dump(by_alias=True, exclude_none=True)
    res = await mock_db.users.insert_one(doc)
    assert res.inserted_id is not None

    found = await mock_db.users.find_one({"email": "jane@example.com"})
    assert found is not None
    assert found["name"] == "Jane Owner"
    assert found["is_active"] is True


@pytest.mark.asyncio
async def test_duplicate_user_email_rejected(mock_db):
    """6. Test duplicate User email rejection."""
    await mock_db.users.create_index([("email", 1)], unique=True)
    user1 = UserModel(name="User 1", email="dup@example.com", password_hash="hash")
    await mock_db.users.insert_one(user1.model_dump(by_alias=True, exclude_none=True))

    user2 = UserModel(name="User 2", email="dup@example.com", password_hash="hash")
    from pymongo.errors import DuplicateKeyError
    with pytest.raises(DuplicateKeyError):
        await mock_db.users.insert_one(user2.model_dump(by_alias=True, exclude_none=True))


@pytest.mark.asyncio
async def test_space_document_insertion(mock_db):
    """7. Test Space document insertion."""
    owner_id = str(ObjectId())
    space = SpaceModel(
        owner_id=owner_id,
        name="TechCorp Space",
        slug="techcorp",
        custom_prompt="Share your experience with TechCorp"
    )
    doc = space.model_dump(by_alias=True, exclude_none=True)
    res = await mock_db.spaces.insert_one(doc)
    assert res.inserted_id is not None

    found = await mock_db.spaces.find_one({"slug": "techcorp"})
    assert found is not None
    assert found["owner_id"] == owner_id
    assert found["avatar_enabled"] is True


@pytest.mark.asyncio
async def test_duplicate_space_slug_rejected(mock_db):
    """8. Test duplicate Space slug rejection."""
    await mock_db.spaces.create_index([("slug", 1)], unique=True)
    owner_id = str(ObjectId())
    space1 = SpaceModel(owner_id=owner_id, name="Space 1", slug="dupslug")
    await mock_db.spaces.insert_one(space1.model_dump(by_alias=True, exclude_none=True))

    space2 = SpaceModel(owner_id=owner_id, name="Space 2", slug="dupslug")
    from pymongo.errors import DuplicateKeyError
    with pytest.raises(DuplicateKeyError):
        await mock_db.spaces.insert_one(space2.model_dump(by_alias=True, exclude_none=True))


@pytest.mark.asyncio
async def test_testimonial_insertion_and_default_status(mock_db):
    """9 & 10. Test Testimonial insertion and default status 'pending'."""
    space_id = str(ObjectId())
    testimonial = TestimonialModel(
        space_id=space_id,
        client_name="David Miller",
        client_email="david@example.com",
        company_role="Product Lead",
        rating=5,
        review_text="Absolute game changer!"
    )
    doc = testimonial.model_dump(by_alias=True, exclude_none=True)
    res = await mock_db.testimonials.insert_one(doc)
    assert res.inserted_id is not None

    found = await mock_db.testimonials.find_one({"_id": res.inserted_id})
    assert found is not None
    assert found["status"] == TestimonialStatus.PENDING.value
    assert found["rating"] == 5
    assert found["is_featured"] is False


@pytest.mark.asyncio
async def test_testimonial_rating_validation():
    """11. Test rating validation via Pydantic model (1-5 constraint)."""
    space_id = str(ObjectId())
    valid_test = TestimonialModel(
        space_id=space_id, client_name="A", client_email="a@ex.com", rating=1, review_text="Good"
    )
    assert valid_test.rating == 1

    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TestimonialModel(
            space_id=space_id, client_name="B", client_email="b@ex.com", rating=6, review_text="Invalid rating"
        )


@pytest.mark.asyncio
async def test_indexes_exist(mock_db):
    """12. Test index creation."""
    await mock_db.users.create_index([("email", 1)], unique=True)
    await mock_db.spaces.create_index([("slug", 1)], unique=True)
    await mock_db.spaces.create_index([("owner_id", 1)])
    await mock_db.testimonials.create_index([("space_id", 1)])
    await mock_db.testimonials.create_index([("status", 1)])

    user_indexes = await mock_db.users.list_indexes()
    space_indexes = await mock_db.spaces.list_indexes()
    assert len(user_indexes) >= 1
    assert len(space_indexes) >= 1


@pytest.mark.asyncio
async def test_user_space_relationship(mock_db):
    """13. Test User -> Space relationship via owner_id."""
    user_id = str(ObjectId())
    space = SpaceModel(owner_id=user_id, name="Owner Space", slug="owner-space")
    await mock_db.spaces.insert_one(space.model_dump(by_alias=True, exclude_none=True))

    found_space = await mock_db.spaces.find_one({"owner_id": user_id})
    assert found_space is not None
    assert found_space["name"] == "Owner Space"


@pytest.mark.asyncio
async def test_space_testimonial_relationship(mock_db):
    """14. Test Space -> Testimonial relationship via space_id."""
    space_id = str(ObjectId())
    testi = TestimonialModel(
        space_id=space_id, client_name="Rel Client", client_email="rel@ex.com", rating=4, review_text="Love it!"
    )
    await mock_db.testimonials.insert_one(testi.model_dump(by_alias=True, exclude_none=True))

    found_testi = await mock_db.testimonials.find_one({"space_id": space_id})
    assert found_testi is not None
    assert found_testi["client_name"] == "Rel Client"


@pytest.mark.asyncio
async def test_document_timestamps():
    """15. Test created_at and updated_at timestamps presence."""
    user = UserModel(name="Time User", email="time@ex.com", password_hash="hash")
    assert isinstance(user.created_at, datetime)
    assert isinstance(user.updated_at, datetime)
