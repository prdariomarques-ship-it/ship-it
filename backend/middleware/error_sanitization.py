"""Error sanitization middleware — return generic 5xx, log full exceptions."""

import traceback

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from utils.logging import get_logger

logger = get_logger(__name__)


class ErrorSanitizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            correlation_id = request.headers.get("x-request-id", "unknown")

            logger.error(
                "Unhandled exception in request",
                extra={
                    "context": {
                        "correlation_id": correlation_id,
                        "method": request.method,
                        "path": request.url.path,
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                },
            )

            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
            )
