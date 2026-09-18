from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("app.http")

QUIET_EXACT = {"/health", "/docs", "/redoc", "/openapi.json", "/api-docs"}


def _is_quiet(path: str) -> bool:
    if path in QUIET_EXACT:
        return True
    return path.startswith("/media")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        path = request.url.path
        status = response.status_code
        message = f"{request.method} {path} -> {status} {elapsed_ms:.0f}ms"
        if status >= 400 or (path.startswith("/api") and not _is_quiet(path)):
            logger.info(message)
        else:
            logger.debug(message)
        return response
