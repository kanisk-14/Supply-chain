"""Health endpoint tests (application starts, envelope shape, DB probe).

- Application starts and exposes /health, /docs, /redoc, /openapi.json.
- The health response uses the canonical success envelope.
- The database probe reports ``ok``/``error`` without leaking internals.
"""

from app.main import API_PREFIX, APP_TITLE, create_app


class TestApplicationStarts:
    def test_app_name(self):
        assert create_app().title == APP_TITLE

    def test_api_prefix_established(self):
        assert API_PREFIX == "/api/v1"


class TestHealthEndpoint:
    def test_health_envelope(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "ok"
        assert body["message"]

    def test_health_database_probe_safe(self, client):
        response = client.get("/health")
        body = response.json()
        assert body["data"]["database"] in {"ok", "error"}
        if body["data"]["database"] == "error":
            assert "Traceback" not in response.text

    def test_openapi_discoverable(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == APP_TITLE
        assert "/health" in schema["paths"]

    def test_docs_pages(self, client):
        for path in ("/docs", "/redoc"):
            response = client.get(path)
            assert response.status_code == 200