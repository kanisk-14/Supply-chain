"""Users endpoint integration tests.

Users are never hard-deleted: deactivation flips ``is_active``. Password hashes
must never appear in any response.
"""

import pytest

from app.modules.users.models import User, UserRole
from tests.conftest import login


def _admin_headers(api_client, seed):
    account = seed.user("root@admin.com", role=UserRole.ADMIN)
    token = login(api_client, account["email"], account["password"])
    return {"Authorization": f"Bearer {token}"}


class TestUserCRUD:
    @pytest.mark.db
    def test_create_user(self, api_client, seed):
        headers = _admin_headers(api_client, seed)
        response = api_client.post(
            "/api/v1/users",
            json={
                "name": "Jane Doe",
                "email": "jane@example.com",
                "password": "Sup3rsecret!",
                "role": "WAREHOUSE_MANAGER",
            },
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["email"] == "jane@example.com"
        assert data["role"] == "WAREHOUSE_MANAGER"
        assert data["is_active"] is True
        assert "password" not in str(data)

    @pytest.mark.db
    def test_create_defaults_role_to_analyst(self, api_client, seed):
        headers = _admin_headers(api_client, seed)
        response = api_client.post(
            "/api/v1/users",
            json={
                "name": "Default Role",
                "email": "default@example.com",
                "password": "Sup3rsecret!",
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["data"]["role"] == "ANALYST"

    @pytest.mark.db
    def test_duplicate_email_conflict(self, api_client, seed):
        seed.user("dup@example.com", role=UserRole.ADMIN)
        headers = _admin_headers(api_client, seed)
        first = api_client.post(
            "/api/v1/users",
            json={
                "name": "A",
                "email": "dup@example.com",
                "password": "Sup3rsecret!",
            },
            headers=headers,
        )
        assert first.status_code == 409
        assert first.json()["error"]["code"] == "CONFLICT"

    @pytest.mark.db
    def test_list_users_paged_envelope(self, api_client, seed):
        for i in range(3):
            seed.user(f"list{i}@example.com")
        headers = _admin_headers(api_client, seed)
        response = api_client.get("/api/v1/users", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["meta"]["page"] == 1
        assert body["meta"]["limit"] == 25
        assert body["meta"]["total"] >= 4
        assert "password" not in str(body["data"])

    @pytest.mark.db
    def test_list_users_filters(self, api_client, seed):
        seed.user("f1@example.com", role=UserRole.ANALYST)
        seed.user("f2@example.com", role=UserRole.ADMIN)
        headers = _admin_headers(api_client, seed)
        response = api_client.get(
            "/api/v1/users", params={"role": "ANALYST"}, headers=headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(u["role"] == "ANALYST" for u in data)

    @pytest.mark.db
    def test_get_user(self, api_client, seed):
        target = seed.user("target@example.com")
        headers = _admin_headers(api_client, seed)
        response = api_client.get(f"/api/v1/users/{target['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["email"] == "target@example.com"

    @pytest.mark.db
    def test_get_missing_user_404(self, api_client, seed):
        headers = _admin_headers(api_client, seed)
        response = api_client.get("/api/v1/users/99999", headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    @pytest.mark.db
    def test_patch_user_soft_deactivation(self, api_client, seed, session_factory):
        target = seed.user("off@example.com")
        headers = _admin_headers(api_client, seed)
        response = api_client.patch(
            f"/api/v1/users/{target['id']}",
            json={"is_active": False},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is False

        with session_factory() as db:
            from sqlalchemy import select

            row = db.execute(select(User).where(User.id == target["id"])).scalar_one()
            assert row.is_active is False

    @pytest.mark.db
    def test_patch_user_role_change(self, api_client, seed):
        target = seed.user("role@example.com", role=UserRole.ANALYST)
        headers = _admin_headers(api_client, seed)
        response = api_client.patch(
            f"/api/v1/users/{target['id']}",
            json={"role": "SUPPLY_CHAIN_MANAGER"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["role"] == "SUPPLY_CHAIN_MANAGER"

    @pytest.mark.db
    def test_patch_user_email_conflict(self, api_client, seed):
        seed.user("taken@example.com")
        target = seed.user("me@example.com")
        headers = _admin_headers(api_client, seed)
        response = api_client.patch(
            f"/api/v1/users/{target['id']}",
            json={"email": "taken@example.com"},
            headers=headers,
        )
        assert response.status_code == 409

    @pytest.mark.db
    def test_patch_reset_password_allows_relogin(self, api_client, seed):
        target = seed.user("pwd@example.com", password="OldPass123!")
        headers = _admin_headers(api_client, seed)
        response = api_client.patch(
            f"/api/v1/users/{target['id']}",
            json={"password": "NewPass456!"},
            headers=headers,
        )
        assert response.status_code == 200
        assert "password" not in str(response.json()["data"])
        # old password no longer works
        old = api_client.post(
            "/api/v1/auth/login",
            json={"email": "pwd@example.com", "password": "OldPass123!"},
        )
        assert old.status_code == 401
        # new password allows login
        assert login(api_client, "pwd@example.com", "NewPass456!") is not None


class TestNoEscalation:
    @pytest.mark.db
    def test_admin_cannot_change_own_role(self, api_client, seed):
        admin = seed.user("boss@admin.com", role=UserRole.ADMIN)
        token = login(api_client, admin["email"], admin["password"])
        response = api_client.patch(
            f"/api/v1/users/{admin['id']}",
            json={"role": "ANALYST"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    @pytest.mark.db
    def test_admin_cannot_deactivate_self(self, api_client, seed):
        admin = seed.user("boss2@admin.com", role=UserRole.ADMIN)
        token = login(api_client, admin["email"], admin["password"])
        response = api_client.patch(
            f"/api/v1/users/{admin['id']}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    @pytest.mark.db
    def test_non_admin_cannot_reach_user_writes(self, api_client, seed):
        analyst = seed.user("low@analyst.com", role=UserRole.ANALYST)
        token = login(api_client, analyst["email"], analyst["password"])
        response = api_client.post(
            "/api/v1/users",
            json={"name": "X", "email": "x@x.com", "password": "Password1!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


class TestUserAudit:
    @pytest.mark.db
    def test_user_create_and_update_are_audited(self, api_client, seed, session_factory):
        from sqlalchemy import select

        from app.modules.audit_logs.models import AuditLog

        headers = _admin_headers(api_client, seed)
        created = api_client.post(
            "/api/v1/users",
            json={"name": "Audit Me", "email": "audit@example.com", "password": "Sup3rsecret!"},
            headers=headers,
        ).json()["data"]
        api_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"name": "Audited Name"},
            headers=headers,
        )

        with session_factory() as db:
            entries = db.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "user",
                    AuditLog.entity_id == created["id"],
                )
            ).scalars().all()
            actions = {e.action for e in entries}
            assert "USER.CREATE" in actions
            assert "USER.UPDATE" in actions