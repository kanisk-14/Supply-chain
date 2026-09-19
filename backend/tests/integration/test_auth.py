"""Login + /me integration tests (real endpoints against the test database)."""

import pytest

from app.modules.users.models import UserRole
from tests.conftest import login


class TestLogin:
    @pytest.mark.db
    def test_login_success_returns_bearer_token(self, api_client, seed):
        seed.user("ops@example.com", role=UserRole.ADMIN, password="SuperSecret1")
        token = login(api_client, "ops@example.com", "SuperSecret1")
        assert isinstance(token, str) and len(token) > 20

    @pytest.mark.db
    def test_login_response_shape(self, api_client, seed):
        seed.user("ops@example.com", password="SuperSecret1")
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "ops@example.com", "password": "SuperSecret1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["token_type"] == "bearer"
        assert body["data"]["access_token"]

    @pytest.mark.db
    def test_login_wrong_password_401(self, api_client, seed):
        seed.user("ops@example.com", password="SuperSecret1")
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "ops@example.com", "password": "WrongPass1"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"

    @pytest.mark.db
    def test_login_unknown_email_401_and_does_not_enumerate(self, api_client):
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "Anything1"},
        )
        assert response.status_code == 401
        body = response.json()["error"]
        assert body["code"] == "UNAUTHORIZED"
        assert "nobody" not in body["message"]

    @pytest.mark.db
    def test_login_inactive_user_rejected(self, api_client, seed):
        seed.user("gone@example.com", password="SuperSecret1", is_active=False)
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "gone@example.com", "password": "SuperSecret1"},
        )
        assert response.status_code == 401

    @pytest.mark.db
    def test_login_email_is_case_insensitive(self, api_client, seed):
        seed.user("Mixed@Example.com", password="SuperSecret1")
        token = login(api_client, "mixed@example.com", "SuperSecret1")
        assert token


class TestMe:
    @pytest.mark.db
    def test_me_returns_current_user_without_password(self, api_client, seed):
        me = seed.user("me@example.com", role=UserRole.WAREHOUSE_MANAGER)
        token = login(api_client, "me@example.com", me["password"])
        response = api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == me["id"]
        assert data["email"] == "me@example.com"
        assert data["role"] == "WAREHOUSE_MANAGER"
        assert "password" not in str(data)
        assert "password_hash" not in str(data)

    @pytest.mark.db
    def test_me_without_token_401(self, api_client):
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.db
    def test_me_with_garbage_token_401(self, api_client):
        response = api_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert response.status_code == 401

    @pytest.mark.db
    def test_me_with_token_for_deleted_user_401(self, api_client, seed):
        import jwt as pyjwt

        from app.core.config import settings

        fake = pyjwt.encode(
            {"sub": "999999", "exp": 9999999999},
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )
        response = api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {fake}"}
        )
        assert response.status_code == 401