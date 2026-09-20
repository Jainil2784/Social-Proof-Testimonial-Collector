# Project 05: Testimonial & Social Proof Collector

A full-stack application for collecting, managing, and embedding testimonials and social proof.

## Tech Stack

- **Backend:** Python, FastAPI, PyMongo Async (`AsyncMongoClient`), Pydantic V2, JWT (future)
- **Database:** MongoDB (`socialproof`) via PyMongo Async API
- **Frontend:** HTML5, CSS3, JavaScript (ES6+), Bootstrap 5
- **API Documentation:** FastAPI Swagger / OpenAPI

---

## Module 1 — MongoDB Database Foundation & Architecture

### Database Management & Indexing
The application uses **MongoDB** as its single, persistent database layer. At FastAPI startup (via lifespan context manager), the `AsyncMongoClient` connects to MongoDB (`MONGODB_URL`), pings the server, selects `MONGODB_DATABASE_NAME`, and initializes indexes across all collections (`users`, `spaces`, `testimonials`).

### Collections & Schema Overview

```
+----------------------------------------+       +----------------------------------------+       +----------------------------------------+
|                 users                  |       |                 spaces                 |       |              testimonials              |
+----------------------------------------+       +----------------------------------------+       +----------------------------------------+
| _id: ObjectId                          | 1   * | _id: ObjectId                          | 1   * | _id: ObjectId                          |
| name: string                           |<----->| owner_id: ObjectId (Index -> users._id)|<----->| space_id: ObjectId (Index->spaces._id) |
| email: string (Unique Index)           |       | name: string                           |       | client_name: string                    |
| password_hash: string                  |       | slug: string (Unique Index)            |       | client_email: string                   |
| is_active: boolean (default: true)     |       | custom_prompt: string/null             |       | company_role: string/null              |
| is_email_verified: boolean (def: false)|       | logo_url: string/null                  |       | rating: integer (1-5, Index)           |
| created_at: datetime                   |       | avatar_enabled: boolean (def: true)    |       | review_text: string                    |
| updated_at: datetime                   |       | rating_enabled: boolean (def: true)    |       | avatar_url: string/null                |
+----------------------------------------+       | custom_questions: array                |       | status: string (pending, approved, etc)|
                                                 | created_at: datetime                   |       | is_featured: boolean (default: false)  |
                                                 | updated_at: datetime                   |       | created_at: datetime (Index)           |
                                                 +----------------------------------------+       | updated_at: datetime                   |
                                                                                                  +----------------------------------------+
```

---

## Directory Structure

```
Com Bot Project/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI lifespan & MongoDB startup
│   │   ├── config.py        # Settings (MONGODB_URL & MONGODB_DATABASE_NAME)
│   │   ├── database.py      # Database layer entry point
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── mongodb.py   # AsyncMongoClient & collection helpers
│   │   │   └── indexes.py   # MongoDB index creation logic
│   │   ├── models/          # MongoDB Pydantic Models
│   │   │   ├── __init__.py
│   │   │   ├── user.py      # UserModel
│   │   │   ├── space.py     # SpaceModel
│   │   │   └── testimonial.py # TestimonialModel & TestimonialStatus enum
│   │   └── schemas/         # Pydantic Schemas
│   │       ├── __init__.py
│   │       ├── user.py      # UserBase, UserCreate, UserResponse
│   │       ├── space.py     # SpaceBase, SpaceCreate, SpaceResponse
│   │       └── testimonial.py # TestimonialBase, TestimonialCreate, TestimonialResponse
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_health.py   # Health & Swagger API tests
│   │   └── test_database.py # MongoDB Pytest database test suite
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── index.html           # Landing page UI
│   ├── css/
│   │   └── style.css        # Stylesheet
│   └── js/
│       └── main.js          # Client JS API caller
├── .env                     # Local environment settings
├── .env.example             # Template environment variables
├── .gitignore               # Git ignore rules
├── pytest.ini               # Pytest configuration
└── README.md                # Project documentation
```

---

## Testing & Verification

Run the full automated Pytest suite for MongoDB:

```powershell
.\venv\Scripts\pytest.exe -v
```
