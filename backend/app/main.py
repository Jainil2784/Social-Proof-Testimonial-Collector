from contextlib import asynccontextmanager
import logging
import os
from typing import Optional
from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from backend.app.api.analytics import router as analytics_router
from backend.app.api.auth import router as auth_router, process_email_verification
from backend.app.api.owner_testimonials import router as owner_testimonials_router
from backend.app.api.spaces import router as spaces_router
from backend.app.api.testimonials import router as testimonials_router
from backend.app.config import settings
from backend.app.db.indexes import create_mongo_indexes
from backend.app.db.mongodb import close_mongo_connection, connect_to_mongo

logger = logging.getLogger(__name__)

# Uploads directory setup
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, "spaces"), exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, "testimonials"), exist_ok=True)

# Frontend directory path
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager handling MongoDB connection and index creation.
    """
    try:
        await connect_to_mongo()
        await create_mongo_indexes()
        logger.info("FastAPI MongoDB database initialization completed.")
    except Exception as e:
        logger.warning(f"MongoDB connection warning at startup: {e}")

    # Verify SMTP configuration at startup (never log passwords!)
    if settings.is_smtp_configured:
        logger.info(
            "SMTP email service CONFIGURED (Host: %s:%s, From: %s <%s>)",
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            settings.SMTP_FROM_NAME,
            settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME,
        )
    else:
        logger.warning(
            "SMTP email service NOT CONFIGURED. Set SMTP_USERNAME and SMTP_PASSWORD in .env to enable email sending."
        )

    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Testimonial & Social Proof Collector API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Exception Handlers for Database Connection Errors
@app.exception_handler(PyMongoError)
@app.exception_handler(ServerSelectionTimeoutError)
async def mongo_exception_handler(request: Request, exc: Exception):
    logger.error(f"MongoDB Connection Error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Database service is unavailable. Please ensure MongoDB is running on your system (mongodb://localhost:27017)."
        }
    )


# Custom CORS middleware that handles all origins including file:// (Origin: null)
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "")

    # Handle CORS preflight (OPTIONS)
    if request.method == "OPTIONS":
        response = JSONResponse(content={}, status_code=200)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            # file:// pages send Origin: null - allow them in dev
            response.headers["Access-Control-Allow-Origin"] = "null"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Cookie, X-Requested-With"
        response.headers["Access-Control-Max-Age"] = "86400"
        return response

    response = await call_next(request)

    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    else:
        response.headers["Access-Control-Allow-Origin"] = "null"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Cookie, X-Requested-With"

    return response

# Mount static uploads directory for logo images & avatars
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Mount frontend static CSS / JS if accessed relative
if os.path.exists(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")

# Include Routers
app.include_router(auth_router)
app.include_router(spaces_router)
app.include_router(testimonials_router)
app.include_router(owner_testimonials_router)
app.include_router(analytics_router)


@app.get("/collect/{space_slug}", response_class=HTMLResponse, tags=["Public Collection"])
async def get_public_collection_page(space_slug: str):
    """
    Public Testimonial Collection Page for a Space slug.
    No authentication required.
    """
    collect_html_path = os.path.join(FRONTEND_DIR, "collect.html")
    if os.path.exists(collect_html_path):
        return FileResponse(collect_html_path)
    return HTMLResponse("<h2>Testimonial Collection Page</h2>", status_code=200)


@app.get("/wall/{space_slug}", response_class=HTMLResponse, tags=["Public Wall of Love"])
async def get_public_wall_page(space_slug: str):
    """
    Public Wall of Love Page for a Space slug.
    No authentication required.
    """
    wall_html_path = os.path.join(FRONTEND_DIR, "wall.html")
    if os.path.exists(wall_html_path):
        return FileResponse(wall_html_path)
    return HTMLResponse("<h2>Wall of Love Page</h2>", status_code=200)


@app.get("/embed/{space_slug}", response_class=HTMLResponse, tags=["Public Embed"])
async def get_public_embed_page(space_slug: str):
    """
    Public Embed Page for a Space slug.
    Designed for iframe embedding across external websites (Grid, Carousel, Badge).
    No authentication required.
    """
    embed_html_path = os.path.join(FRONTEND_DIR, "embed.html")
    if os.path.exists(embed_html_path):
        return FileResponse(embed_html_path)
    return HTMLResponse("<h2>Embed Page</h2>", status_code=200)




@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def get_index():
    """Serve the frontend landing page."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>SocialProof — Frontend not found</h2>", status_code=200)


@app.get("/login", response_class=RedirectResponse, tags=["Frontend"])
async def redirect_login():
    """Redirect /login to landing page with sign-in modal opened."""
    return RedirectResponse(url="/?auth=login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/register", response_class=RedirectResponse, tags=["Frontend"])
async def redirect_register():
    """Redirect /register to landing page with registration modal opened."""
    return RedirectResponse(url="/?auth=register", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/forgot-password", response_class=RedirectResponse, tags=["Frontend"])
@app.get("/reset-password", response_class=RedirectResponse, tags=["Frontend"])
async def redirect_forgot_password(token: Optional[str] = None):
    """Redirect /forgot-password or /reset-password to landing page with password reset modal opened."""
    target = f"/?auth=reset&token={token}" if token else "/?auth=forgot"
    return RedirectResponse(url=target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/verify-email", response_class=RedirectResponse, tags=["Frontend"])
async def handle_verify_email(token: Optional[str] = None):
    """
    Handle email verification link clicks directly from email clients.
    Processes the cryptographic token, marks the account as email_verified in MongoDB,
    and redirects the user to the dedicated /email-verified result page.
    """
    if not token or not token.strip():
        return RedirectResponse(url="/?auth=verify", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    status_key, _ = await process_email_verification(token.strip())
    return RedirectResponse(url=f"/email-verified?status={status_key}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/email-verified", response_class=HTMLResponse, tags=["Frontend"])
async def serve_email_verified_page(token: Optional[str] = None, status: Optional[str] = None):
    """
    Serve the standalone email verification result page.
    If a token is passed without a status, processes it and redirects to /email-verified?status=...
    """
    if token and not status:
        status_key, _ = await process_email_verification(token.strip())
        return RedirectResponse(url=f"/email-verified?status={status_key}", status_code=status.HTTP_303_SEE_OTHER)

    verified_file = os.path.join(FRONTEND_DIR, "email-verified.html")
    if os.path.exists(verified_file):
        return FileResponse(verified_file)
    return HTMLResponse("<h2>Email verification page not found</h2>", status_code=404)


@app.get("/dashboard", response_class=HTMLResponse, tags=["Frontend"])
@app.get("/dashboard.html", response_class=HTMLResponse, tags=["Frontend"])
@app.get("/dashboard/{subpath:path}", response_class=HTMLResponse, tags=["Frontend"])
async def get_dashboard(subpath: str = ""):
    """
    Serve the authenticated owner dashboard.
    Auth is enforced client-side via /api/auth/me.
    Supports deep-linking into dashboard sections.
    """
    dashboard_path = os.path.join(FRONTEND_DIR, "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return HTMLResponse("<h2>Dashboard not found</h2>", status_code=404)


@app.get("/api/health", tags=["Health"])
def health_check():
    """
    Health check endpoint to verify that the application backend is up and running.
    """
    return {
        "status": "healthy",
        "app_name": settings.PROJECT_NAME,
        "version": "1.0.0"
    }
