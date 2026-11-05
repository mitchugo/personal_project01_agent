"""Session 1 scaffold tests.

These check that the skeleton runs and that the example config holds no secret
values. They do NOT test any tenant-isolation or authorisation property.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRET_KEY_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def test_health_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_env_example_has_no_secret_values():
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    settings = [
        line.split("=", 1)
        for line in lines
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    ]

    secret_like = {
        key.strip(): value.strip()
        for key, value in settings
        if any(marker in key.upper() for marker in SECRET_KEY_MARKERS)
    }

    assert secret_like, "expected at least one secret placeholder to check"
    for key, value in secret_like.items():
        assert value == "", f"{key} in .env.example must be empty"
