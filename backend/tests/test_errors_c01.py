from uuid import uuid4

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.testclient import TestClient

from app.errors import APIError, install_error_handlers


def test_api_error_attributes():
    err1 = APIError("CODE_1", "Message 1")
    assert err1.code == "CODE_1"
    assert err1.message == "Message 1"
    assert err1.status == 422
    assert err1.details is None
    assert err1.field_errors == []

    err2 = APIError(
        code="NOT_FOUND",
        message="Resource not found",
        status=404,
        details={"hint": "check id"},
        field_errors=[{"field": "id", "message": "Not found"}],
    )
    assert err2.code == "NOT_FOUND"
    assert err2.message == "Resource not found"
    assert err2.status == 404
    assert err2.details == {"hint": "check id"}
    assert err2.field_errors == [{"field": "id", "message": "Not found"}]


def test_domain_error_envelope_c01_compliance():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/test-domain-error-simple")
    def simple_err():
        raise APIError("SIMPLE_ERROR", "Simple message", 400)

    @app.get("/test-domain-error-detailed")
    def detailed_err():
        raise APIError(
            "DETAILED_ERROR",
            "Detailed message",
            409,
            details={"current_revision": 5},
            field_errors=[{"field": "revision", "message": "Conflict"}],
        )

    client = TestClient(app)

    # 1. Simple error without details
    req_id = str(uuid4())
    res1 = client.get("/test-domain-error-simple", headers={"X-Request-ID": req_id})
    assert res1.status_code == 400
    body1 = res1.json()
    assert "error" in body1
    err_obj1 = body1["error"]
    assert err_obj1["code"] == "SIMPLE_ERROR"
    assert err_obj1["message"] == "Simple message"
    assert err_obj1["request_id"] == req_id
    assert err_obj1["field_errors"] == []
    assert "details" not in err_obj1

    # 2. Detailed error with details and field_errors
    res2 = client.get("/test-domain-error-detailed", headers={"X-Request-ID": req_id})
    assert res2.status_code == 409
    body2 = res2.json()
    assert "error" in body2
    err_obj2 = body2["error"]
    assert err_obj2["code"] == "DETAILED_ERROR"
    assert err_obj2["message"] == "Detailed message"
    assert err_obj2["request_id"] == req_id
    assert err_obj2["details"] == {"current_revision": 5}
    assert err_obj2["field_errors"] == [{"field": "revision", "message": "Conflict"}]


def test_request_validation_error_normalizes_loc():
    app = FastAPI()
    install_error_handlers(app)

    class Nested(BaseModel):
        count: int

    class Payload(BaseModel):
        name: str
        nested: Nested

    @app.post("/test-validation")
    def val_endpoint(data: Payload):
        return {"status": "ok"}

    client = TestClient(app)
    req_id = str(uuid4())
    res = client.post(
        "/test-validation",
        headers={"X-Request-ID": req_id},
        json={"name": 123, "nested": {"count": "not-an-int"}},
    )

    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["message"] == "Проверьте поля запроса."
    assert err["request_id"] == req_id

    # Normalized fields must not contain "body" prefix
    fields = [fe["field"] for fe in err["field_errors"]]
    for f in fields:
        assert not f.startswith("body"), f"Unexpected body prefix in {f}"
    assert "nested.count" in fields

    # details matches field_errors for full backward compatibility
    assert err["details"] == err["field_errors"]


def test_unhandled_exception_returns_internal_error_500():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/test-crash")
    def crash():
        raise RuntimeError("SELECT password_hash FROM secret_table WHERE id=1")

    # Starlette TestClient with raise_server_exceptions=False tests the 500 handler
    client = TestClient(app, raise_server_exceptions=False)
    req_id = str(uuid4())
    res = client.get("/test-crash", headers={"X-Request-ID": req_id})

    assert res.status_code == 500
    assert res.headers.get("X-Request-ID") == req_id
    body = res.json()
    assert body == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Внутренняя ошибка сервера. Обратитесь к администратору.",
            "request_id": req_id,
            "details": None,
            "field_errors": [],
        }
    }
    # Ensure sensitive database/traceback info is hidden from external client
    assert "secret_table" not in res.text
    assert "Traceback" not in res.text


def test_validation_preserves_field_named_body():
    app = FastAPI()
    install_error_handlers(app)

    class Comment(BaseModel):
        body: str
        author: str

    class Post(BaseModel):
        comment: Comment

    @app.post("/test-body-field")
    def post_endpoint(data: Post):
        return {"ok": True}

    client = TestClient(app)
    # Missing 'body' inside comment: loc is ('body', 'comment', 'body')
    res = client.post("/test-body-field", json={"comment": {"author": "Alice"}})
    assert res.status_code == 422
    err = res.json()["error"]
    fields = [fe["field"] for fe in err["field_errors"]]
    assert "comment.body" in fields

    @app.post("/test-direct-body")
    def direct_endpoint(data: Comment):
        return {"ok": True}

    # Missing direct 'body' field: loc is ('body', 'body') -> should normalize to 'body', not ''
    res2 = client.post("/test-direct-body", json={"author": "Bob"})
    assert res2.status_code == 422
    err2 = res2.json()["error"]
    fields2 = [fe["field"] for fe in err2["field_errors"]]
    assert "body" in fields2


def test_empty_body_and_malformed_json():
    app = FastAPI()
    install_error_handlers(app)

    class Payload(BaseModel):
        title: str

    @app.post("/test-payload")
    def payload_endpoint(data: Payload):
        return {"ok": True}

    client = TestClient(app)
    # Empty body
    res_empty = client.post("/test-payload", content=b"", headers={"Content-Type": "application/json"})
    assert res_empty.status_code == 422
    assert res_empty.json()["error"]["code"] == "VALIDATION_ERROR"

    # Malformed JSON
    res_bad = client.post("/test-payload", content=b"invalid{json", headers={"Content-Type": "application/json"})
    assert res_bad.status_code == 422
    assert res_bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_error_handlers_safe_with_mock_request():
    import asyncio

    app = FastAPI()
    install_error_handlers(app)

    domain_handler = app.exception_handlers[APIError]
    internal_handler = app.exception_handlers[Exception]

    class NakedRequest:
        pass

    req = NakedRequest()

    res_domain = asyncio.run(domain_handler(req, APIError("ERR", "msg", 400)))
    assert res_domain.status_code == 400
    assert "X-Request-ID" in res_domain.headers

    res_internal = asyncio.run(internal_handler(req, RuntimeError("fail")))
    assert res_internal.status_code == 500
    assert "X-Request-ID" in res_internal.headers


def test_query_path_header_validation_normalization():
    from fastapi import Header, Path, Query

    app = FastAPI()
    install_error_handlers(app)

    @app.get("/items/{item_id}")
    def item_endpoint(
        item_id: int = Path(...),
        page: int = Query(..., ge=1),
        x_custom: int = Header(..., alias="X-Custom"),
    ):
        return {"ok": True}

    client = TestClient(app)
    req_id = str(uuid4())

    # Invalid path, query, and header parameters simultaneously
    res = client.get(
        "/items/not-an-int?page=invalid-page",
        headers={"X-Custom": "invalid-header", "X-Request-ID": req_id},
    )
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["request_id"] == req_id

    fields = [fe["field"] for fe in err["field_errors"]]
    # All location prefixes ('path', 'query', 'header') must be stripped
    assert "item_id" in fields
    assert "page" in fields
    assert "X-Custom" in fields
    for f in fields:
        assert not f.startswith("path.")
        assert not f.startswith("query.")
        assert not f.startswith("header.")


def test_api_error_headers_and_status_code_alias():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/rate-limited")
    def rate_limited():
        raise APIError(
            code="RATE_LIMITED",
            message="Превышен лимит запросов. Попробуйте позже.",
            status=429,
            headers={"Retry-After": "60"},
        )

    @app.get("/status-code-kwarg")
    def status_code_kwarg():
        raise APIError(
            code="BAD_REQUEST",
            message="Некорректный запрос.",
            status_code=400,
        )

    client = TestClient(app)
    req_id = str(uuid4())

    res1 = client.get("/rate-limited", headers={"X-Request-ID": req_id})
    assert res1.status_code == 429
    assert res1.headers.get("Retry-After") == "60"
    assert res1.headers.get("X-Request-ID") == req_id
    assert res1.json()["error"]["code"] == "RATE_LIMITED"

    res2 = client.get("/status-code-kwarg")
    assert res2.status_code == 400
    assert res2.json()["error"]["code"] == "BAD_REQUEST"

    # Verify status_code property getter and setter
    err = APIError("TEST", "msg", status=403)
    assert err.status == 403
    assert err.status_code == 403
    err.status_code = 418
    assert err.status == 418
    assert err.status_code == 418


def test_validation_error_with_none_or_missing_loc_fields():
    import asyncio
    from fastapi.exceptions import RequestValidationError

    app = FastAPI()
    install_error_handlers(app)
    val_handler = app.exception_handlers[RequestValidationError]

    class MockRequest:
        headers = {"x-request-id": "case-insensitive-id-123"}

    # Validation error with loc=None, msg=None, empty errors
    exc = RequestValidationError(errors=[
        {"loc": None, "msg": None, "type": "error_type"},
        {"loc": (), "msg": "empty loc error", "type": "error_type"},
    ])

    res = asyncio.run(val_handler(MockRequest(), exc))
    assert res.status_code == 422
    import json
    data = json.loads(res.body)
    err = data["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["request_id"] == "case-insensitive-id-123"
    assert len(err["field_errors"]) == 2
    assert err["field_errors"][0]["field"] == ""
    assert err["field_errors"][0]["message"] == ""
    assert err["field_errors"][1]["field"] == ""
    assert err["field_errors"][1]["message"] == "empty loc error"


def test_domain_error_with_complex_types_in_details():
    from datetime import datetime, timezone
    from decimal import Decimal

    app = FastAPI()
    install_error_handlers(app)

    fixed_uuid = uuid4()
    fixed_time = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)

    @app.get("/test-complex-details")
    def complex_details_ep():
        raise APIError(
            code="RESOURCE_STATE_ERROR",
            message="Ошибка состояния ресурса",
            status=422,
            details={
                "resource_id": fixed_uuid,
                "timestamp": fixed_time,
                "amount": Decimal("99.95"),
                "flags": {"flag_a", "flag_b"},
            },
            field_errors=[
                {"field": "resource_id", "message": f"Invalid id: {fixed_uuid}"}
            ],
        )

    client = TestClient(app)
    req_id = str(uuid4())
    res = client.get("/test-complex-details", headers={"X-Request-ID": req_id})
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    err = data["error"]
    assert err["code"] == "RESOURCE_STATE_ERROR"
    assert err["details"]["resource_id"] == str(fixed_uuid)
    assert "2026-09-21" in err["details"]["timestamp"]
    assert err["details"]["amount"] == 99.95
    assert isinstance(err["details"]["flags"], list)
    assert set(err["details"]["flags"]) == {"flag_a", "flag_b"}
    assert err["field_errors"][0]["field"] == "resource_id"


def test_api_error_string_status_coercion():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/string-status")
    def str_status_ep():
        raise APIError(
            code="BAD_INPUT",
            message="Неверный ввод",
            status="400",  # string status coerced to int
        )

    client = TestClient(app)
    res = client.get("/string-status")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_INPUT"


def test_header_case_insensitive_deduplication():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/custom-req-id-header")
    def custom_header_ep():
        raise APIError(
            code="CUSTOM_ID",
            message="Custom correlation",
            status=403,
            headers={"x-request-id": "custom-override-id-999"},
        )

    client = TestClient(app)
    res = client.get("/custom-req-id-header")
    assert res.status_code == 403
    # Header should be overridden without duplicating on raw wire
    assert res.headers.get("x-request-id") == "custom-override-id-999"


def test_validation_error_with_non_dict_error_objects():
    import asyncio
    from fastapi.exceptions import RequestValidationError

    app = FastAPI()
    install_error_handlers(app)
    val_handler = app.exception_handlers[RequestValidationError]

    class MockErrorObject:
        def __init__(self, loc, msg):
            self.loc = loc
            self.msg = msg

    exc = RequestValidationError(errors=[
        MockErrorObject(loc=("body", "non_dict_field"), msg="custom msg"),
    ])

    class MockReq:
        headers = {"x-request-id": "obj-req-1"}

    res = asyncio.run(val_handler(MockReq(), exc))
    assert res.status_code == 422
    import json
    data = json.loads(res.body)
    assert data["error"]["field_errors"][0]["field"] == "non_dict_field"
    assert data["error"]["field_errors"][0]["message"] == "custom msg"



