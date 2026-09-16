from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import config

# Always public (Render health checks + optional docs discovery).
PUBLIC_EXACT = {"/health"}
PUBLIC_PREFIXES = ()

# Protect JSON/API surface. /media stays open so video players can load outputUrl without custom headers.
PROTECTED_PREFIXES = ("/api",)


def _extract_api_key(request: Request) -> str:
    header_key = (request.headers.get("x-api-key") or "").strip()
    if header_key:
        return header_key
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # Query fallback for tools that cannot set headers
    return (request.query_params.get("api_key") or "").strip()


def _is_public(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def _is_protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PROTECTED_PREFIXES)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or _is_public(path) or not _is_protected(path):
            return await call_next(request)

        expected = config.manifestia_api_key
        if not expected:
            # Fail closed in production so a missing key cannot leave APIs open.
            if config.node_env.lower() == "production":
                return JSONResponse(
                    status_code=503,
                    content={"error": "API auth not configured (MANIFESTIA_API_KEY missing)"},
                )
            return await call_next(request)

        provided = _extract_api_key(request)
        if (
            not provided
            or len(provided) != len(expected)
            or not secrets.compare_digest(provided, expected)
        ):
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "hint": "Send X-API-Key or Authorization: Bearer <MANIFESTIA_API_KEY>"},
            )
        return await call_next(request)
