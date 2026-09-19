"""Consistent response envelope and pagination tests."""

from app.common.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    resolve_pagination,
    pagination_meta,
)
from app.common.responses import (
    build_error_response,
    build_paged_response,
    build_success_response,
)


class TestResponseEnvelope:
    def test_success_shape(self):
        payload = build_success_response({"a": 1})
        assert payload == {
            "success": True,
            "data": {"a": 1},
            "message": "Operation successful",
        }

    def test_success_custom_message(self):
        payload = build_success_response([1, 2], message="Done")
        assert payload["message"] == "Done"
        assert payload["data"] == [1, 2]
        assert payload["success"] is True

    def test_paged_shape(self):
        payload = build_paged_response(["a", "b"], page=2, limit=25, total=50)
        assert payload["success"] is True
        assert payload["data"] == ["a", "b"]
        assert payload["meta"] == {"page": 2, "limit": 25, "total": 50, "pages": 2}
        assert payload["message"] == "Operation successful"

    def test_error_shape(self):
        payload = build_error_response("NOT_FOUND", "missing", details={"id": 5})
        assert payload["success"] is False
        assert payload["error"] == {
            "code": "NOT_FOUND",
            "message": "missing",
            "details": {"id": 5},
        }

    def test_error_without_details_omits_key(self):
        payload = build_error_response("CONFLICT", "nope")
        assert "details" not in payload["error"]


class TestPagination:
    def test_defaults(self):
        page, limit = resolve_pagination(None, None)
        assert page == 1
        assert limit == DEFAULT_LIMIT

    def test_zero_falls_back_to_defaults(self):
        # 0/None mean "use the default" for both page and limit.
        page, limit = resolve_pagination(0, 0)
        assert page == 1
        assert limit == DEFAULT_LIMIT

    def test_negative_values_clamped_to_floor(self):
        page, limit = resolve_pagination(-3, -5)
        assert page == 1
        assert limit == 1

    def test_clamps_over_max_limit(self):
        page, limit = resolve_pagination(1, 10_000)
        assert limit == MAX_LIMIT

    def test_resolves_positive_values(self):
        assert resolve_pagination(5, 50) == (5, 50)

    def test_pagination_meta(self):
        assert pagination_meta(1, 25, 100) == {"page": 1, "limit": 25, "total": 100, "pages": 4}
        assert pagination_meta(1, 25, 0)["pages"] == 0