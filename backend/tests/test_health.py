from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_check():
    """Verify that GET /api/health returns 200 OK and valid JSON."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app_name" in data
    assert "version" in data


def test_openapi_docs():
    """Verify OpenAPI schema is accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/health" in schema["paths"]
