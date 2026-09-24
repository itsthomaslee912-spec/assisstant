import os

os.environ.setdefault("INITIAL_ADMIN_EMAIL", "test-admin@example.com")
os.environ.setdefault("INITIAL_ADMIN_USER_ID", "test-admin-v2")
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "test-password-123")

from fastapi.testclient import TestClient

from app.main import app


def test_seeded_admin_can_sign_in():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"identity": "test-admin-v2", "password": "test-password-123"})
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "admin"


def test_invalid_user_cannot_sign_in():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"identity": "missing", "password": "wrong"})
        assert response.status_code == 401
