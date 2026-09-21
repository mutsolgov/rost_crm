import logging
from uuid import uuid4

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

PREFIXES = ("body", "query", "path", "header", "cookie")


class APIError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 422,
        details=None,
        field_errors: list | None = None,
        headers: dict[str, str] | None = None,
        status_code: int | None = None,
    ):
        self.code = code
        self.message = message
        raw_status = status_code if status_code is not None else status
        try:
            self.status = int(raw_status)
        except (ValueError, TypeError):
            self.status = 422
        self.details = details
        self.field_errors = list(field_errors) if field_errors else []
        self.headers = dict(headers) if headers else {}

    @property
    def status_code(self) -> int:
        return self.status

    @status_code.setter
    def status_code(self, value: int) -> None:
        try:
            self.status = int(value)
        except (ValueError, TypeError):
            self.status = 422


def _get_request_id(request: Request | None) -> str:
    if request is not None:
        state = getattr(request, "state", None)
        if state is not None:
            req_id = getattr(state, "request_id", None)
            if req_id:
                return str(req_id)
        headers = getattr(request, "headers", None)
        if headers is not None:
            if hasattr(headers, "get"):
                req_id = headers.get("X-Request-ID") or headers.get("x-request-id")
                if req_id:
                    return str(req_id)
            if isinstance(headers, dict):
                for k, v in headers.items():
                    if isinstance(k, str) and k.lower() == "x-request-id" and v:
                        return str(v)
            if isinstance(headers, (list, tuple)):
                for item in headers:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        k, v = item
                        k_str = k.decode() if isinstance(k, bytes) else str(k)
                        if k_str.lower() == "x-request-id" and v:
                            return v.decode() if isinstance(v, bytes) else str(v)
    return str(uuid4())


def install_error_handlers(app):
    @app.exception_handler(APIError)
    async def domain_error(request: Request, exc: APIError):
        req_id = _get_request_id(request)
        error = {
            "code": exc.code,
            "message": exc.message,
            "request_id": req_id,
        }
        if exc.details is not None:
            try:
                error["details"] = jsonable_encoder(exc.details)
            except Exception:
                error["details"] = exc.details
        fe = getattr(exc, "field_errors", []) or []
        try:
            error["field_errors"] = jsonable_encoder(fe)
        except Exception:
            error["field_errors"] = list(fe)

        resp_headers = {"X-Request-ID": req_id}
        if getattr(exc, "headers", None):
            for k, v in exc.headers.items():
                if isinstance(k, str) and k.lower() == "x-request-id":
                    resp_headers["X-Request-ID"] = str(v)
                else:
                    resp_headers[str(k)] = str(v)

        status = getattr(exc, "status_code", getattr(exc, "status", 422))
        try:
            status_val = int(status)
        except (ValueError, TypeError):
            status_val = 422
        return JSONResponse({"error": error}, status_code=status_val, headers=resp_headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        field_errors = []
        for e in exc.errors():
            if isinstance(e, dict):
                loc = e.get("loc") or ()
                msg = e.get("msg") or ""
            else:
                loc = getattr(e, "loc", None) or ()
                msg = getattr(e, "msg", None) or ""
            if loc and loc[0] in PREFIXES:
                loc = loc[1:]
            field_errors.append(
                {
                    "field": ".".join(str(p) for p in loc),
                    "message": str(msg),
                }
            )
        return await domain_error(
            request,
            APIError("VALIDATION_ERROR", "Проверьте поля запроса.", 422, details=field_errors, field_errors=field_errors),
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        logger.exception("Unhandled server error: %s", exc)
        req_id = _get_request_id(request)
        return JSONResponse(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Внутренняя ошибка сервера. Обратитесь к администратору.",
                    "request_id": req_id,
                    "details": None,
                    "field_errors": [],
                }
            },
            status_code=500,
            headers={"X-Request-ID": req_id},
        )


