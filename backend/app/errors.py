from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, code, message, status=422, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details


def install_error_handlers(app):
    @app.exception_handler(APIError)
    async def domain_error(request: Request, exc: APIError):
        error = {"code": exc.code, "message": exc.message,
                 "request_id": getattr(request.state, "request_id", str(uuid4()))}
        if exc.details is not None:
            error["details"] = exc.details
        return JSONResponse({"error": error}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
                   for e in exc.errors()]
        return await domain_error(request, APIError("VALIDATION_ERROR", "Проверьте поля запроса.", 422, details))
