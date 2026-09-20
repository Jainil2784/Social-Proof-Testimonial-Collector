"""
Tests for Module 9 — Frontend Integration & Direct URL Routing
Verifies that all frontend pages, direct routes, and redirects function cleanly.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client():
    # Use follow_redirects=False to verify redirect responses explicitly
    return TestClient(app, follow_redirects=False)


def test_get_landing_page(client):
    """GET / should serve the frontend landing page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "SocialProof" in response.text or "Social" in response.text


def test_redirect_login(client):
    """GET /login should redirect to /?auth=login."""
    response = client.get("/login")
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/?auth=login"


def test_redirect_register(client):
    """GET /register should redirect to /?auth=register."""
    response = client.get("/register")
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/?auth=register"


def test_redirect_forgot_password(client):
    """GET /forgot-password should redirect to /?auth=forgot."""
    response = client.get("/forgot-password")
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/?auth=forgot"


def test_redirect_reset_password(client):
    """GET /reset-password should redirect to /?auth=forgot."""
    response = client.get("/reset-password")
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/?auth=forgot"


def test_redirect_verify_email(client):
    """GET /verify-email should redirect to /?auth=verify."""
    response = client.get("/verify-email")
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/?auth=verify"


def test_get_dashboard(client):
    """GET /dashboard should serve the owner dashboard HTML."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "data-section=\"home\"" in response.text


def test_get_dashboard_html_direct(client):
    """GET /dashboard.html should serve the owner dashboard HTML."""
    response = client.get("/dashboard.html")
    assert response.status_code == 200
    assert "Dashboard" in response.text


def test_get_dashboard_subpath_deep_link(client):
    """GET /dashboard/reviews and /dashboard/analytics should serve dashboard HTML."""
    for subpath in ["reviews", "analytics", "embed", "spaces", "create-space", "profile"]:
        response = client.get(f"/dashboard/{subpath}")
        assert response.status_code == 200
        assert "Dashboard" in response.text


def test_get_public_collect_page_returns_html(client):
    """GET /collect/{slug} should serve the public collection HTML page."""
    response = client.get("/collect/sample-space")
    assert response.status_code == 200
    assert "Submit Testimonial" in response.text or "public-testimonial-form" in response.text


def test_get_public_wall_page_returns_html(client):
    """GET /wall/{slug} should serve the public Wall of Love HTML page."""
    response = client.get("/wall/sample-space")
    assert response.status_code == 200
    assert "Wall of Love" in response.text


def test_get_public_embed_page_returns_html(client):
    """GET /embed/{slug} should serve the public embed HTML page."""
    response = client.get("/embed/sample-space")
    assert response.status_code == 200
    assert "Embed" in response.text or "embed-container" in response.text


def test_get_email_verified_page(client):
    """GET /email-verified should serve the email verification HTML page."""
    response = client.get("/email-verified")
    assert response.status_code == 200
    assert "Email Verification" in response.text
    assert "Email Verified Successfully!" in response.text
    assert "Go to Sign In" in response.text


def test_verify_email_with_token_redirects_to_email_verified(client):
    """GET /verify-email?token=xyz should redirect to /email-verified?status=..."""
    response = client.get("/verify-email?token=some_token", follow_redirects=False)
    assert response.status_code in (307, 302, 303)
    assert response.headers["location"].startswith("/email-verified?status=")
