"""Centralized exception handling tests.

A fresh app is created per test and mounted with throwaway routes that raise the
exceptions the generic handlers are built to catch. This asserts the envelope
and HTTP status codes without touching any database.
"""

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.common.exceptions import (
    ConflictError,
    ForbiddenError,
    InsufficientInventoryError,
    InvalidStateTransitionError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.main import create_app


class DemoModel(BaseModel):
    quantity: int


@pytest.fixture()
def error_app():
    app = create_app()
    router = APIRouter()

    @router.get("/boom/not-found")
    def boom_not_found():
        raise NotFoundError("User not found", details={"id": 999})

    @router.get("/boom/validation")
    def boom_validation():
        raise ValidationError("Invalid payload")

    @router.get("/boom/conflict")
    def boom_conflict():
        raise ConflictError("Duplicate code")

    @router.get("/boom/unauthorized")
    def boom_unauthorized():
        raise UnauthorizedError("Credentials missing")

    @router.get("/boom/forbidden")
    def boom_forbidden():
        raise ForbiddenError("Not allowed")

    @router.get("/boom/invalid-transition")
    def boom_invalid_transition():
        raise InvalidStateTransitionError(
            "order: invalid transition FULFILLED -> PLACED"
        )

    @router.get("/boom/insufficient-inventory")
    def boom_insufficient():
        raise InsufficientInventoryError(
            "Need 5 but only 2 available", details={"available": 2, "required": 5}
        )

    @router.get("/boom/internal")
    def boom_internal():
        raise RuntimeError("secret stack detail")

    @router.post("/boom/validation-model")
    def boom_request_validation(payload: DemoModel):
        return payload

    app.include_router(router)
    # raise_server_exceptions=False lets us assert on the 500 envelope; by
    # default Starlette re-raises the original exception in the test client.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert "success" in body and "data" not in body


class TestMappings:
    @pytest.mark.parametrize(
        "path,status,code",
        [
            ("/boom/not-found", 404, "NOT_FOUND"),
            ("/boom/validation", 400, "VALIDATION_ERROR"),
            ("/boom/conflict", 409, "CONFLICT"),
            ("/boom/unauthorized", 401, "UNAUTHORIZED"),
            ("/boom/forbidden", 403, "FORBIDDEN"),
            ("/boom/invalid-transition", 409, "INVALID_STATE_TRANSITION"),
            ("/boom/insufficient-inventory", 409, "INSUFFICIENT_INVENTORY"),
        ],
    )
    def test_app_errors_map_correctly(self, error_app, path, status, code):
        _assert_error(error_app.get(path), status, code)

    def test_unknown_route_returns_envelope_404(self, error_app):
        _assert_error(error_app.get("/does-not-exist"), 404, "NOT_FOUND")

    def test_pydantic_validation_returns_envelope_422(self, error_app):
        response = error_app.post("/boom/validation-model", json={})
        _assert_error(response, 422, "VALIDATION_ERROR")

    def test_malformed_json_returns_envelope_422(self, error_app):
        response = error_app.post(
            "/boom/validation-model", content="{this is not json"
        )
        _assert_error(response, 422, "VALIDATION_ERROR")

    def test_validation_details_are_json_safe_and_structured(self, error_app):
        response = error_app.post("/boom/validation-model", json={})
        _assert_error(response, 422, "VALIDATION_ERROR")
        details = response.json()["error"]["details"]
        assert isinstance(details, list)
        assert {"field", "message", "type"} <= set(details[0])

    def test_unhandled_exception_hides_stack_and_returns_500(self, error_app):
        response = error_app.get("/boom/internal")
        _assert_error(response, 500, "INTERNAL_ERROR")
        body_text = response.text
        assert "secret stack detail" not in body_text
        assert "Traceback" not in body_text

    def test_error_details_passthrough(self, error_app):
        response = error_app.get("/boom/insufficient-inventory")
        assert response.json()["error"]["details"] == {"available": 2, "required": 5}