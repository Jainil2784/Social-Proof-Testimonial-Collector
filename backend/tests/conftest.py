import pytest
from backend.app.config import settings


@pytest.fixture(autouse=True)
def default_test_env(monkeypatch):
    """
    Ensure general unit test suites from Modules 3-8 can run with standard test fixtures.
    Specific auth tests that verify Gmail-only mode explicitly enable settings.GMAIL_ONLY.
    """
    monkeypatch.setattr(settings, "GMAIL_ONLY", False)
