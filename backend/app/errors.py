"""BE-18: maps internal exceptions to api-spec.md §1.1's standard error envelope."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.action_service import InvalidStateTransition
from app.services.intake_service import ValidationError


def envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ValidationError)
    async def _validation(_req: Request, exc: ValidationError):
        return JSONResponse(status_code=400, content=envelope("VALIDATION_ERROR", exc.message, {"field": exc.field}))

    @app.exception_handler(RequestValidationError)
    async def _schema_validation(_req: Request, exc: RequestValidationError):
        # Pydantic/FastAPI's own 422 schema-validation failures are
        # remapped to api-spec.md §1.1's 400 VALIDATION_ERROR envelope.
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return JSONResponse(
            status_code=400,
            content=envelope("VALIDATION_ERROR", first.get("msg", "invalid request body"), {"field": field}),
        )

    @app.exception_handler(KeyError)
    async def _not_found(_req: Request, exc: KeyError):
        return JSONResponse(status_code=404, content=envelope("NOT_FOUND", f"{exc.args[0]!s} not found"))

    @app.exception_handler(InvalidStateTransition)
    async def _conflict(_req: Request, exc: InvalidStateTransition):
        details = {}
        if exc.current_status is not None:
            details["current_status"] = exc.current_status
        if exc.expected_status is not None:
            details["expected_status"] = exc.expected_status
        return JSONResponse(status_code=409, content=envelope("INVALID_STATE_TRANSITION", exc.message, details))
