from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import MEDIA_URL_PREFIX, MUSIC_URL_PREFIX, config
from app.db.connection import close_db, get_db
from app.lib.music.catalog import get_music_root
from app.logging_setup import setup_logging
from app.middleware.api_key import ApiKeyMiddleware
from app.middleware.request_log import RequestLogMiddleware
from app.routes.auth import router as auth_router
from app.routes.library import router as library_router
from app.routes.media import router as media_router
from app.routes.onboarding import router as onboarding_router
from app.routes.reels import router as reels_router
from app.storage.paths import ensure_storage_root

logger = logging.getLogger(__name__)


def log_seedance_readiness() -> None:
    key_status = "set" if config.byteplus_api_key else "MISSING"
    api_auth = "set" if config.manifestia_api_key else "MISSING"
    logger.info("Seedance pipeline check")
    logger.info("  BYTEPLUS_API_KEY: %s", key_status)
    logger.info("  BYTEPLUS_VIDEO_MODEL: %s", config.byteplus_video_model)
    logger.info("  BYTEPLUS_API_URL: %s", config.byteplus_api_url)
    logger.info("  PUBLIC_API_URL: %s", config.public_api_url)
    logger.info("  MANIFESTIA_API_KEY: %s", api_auth)
    if not config.byteplus_api_key:
        logger.warning("  Status: INCOMPLETE — BYTEPLUS_API_KEY missing (restart after editing .env)")
    else:
        logger.info("  Status: READY for Seedance video generation")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(config.log_level)
    await get_db()
    await ensure_storage_root()
    scheme = "https" if config.ssl_certfile and config.ssl_keyfile else "http"
    logger.info("Manifestia Python backend ready on %s://0.0.0.0:%s", scheme, config.port)
    logger.info("Swagger UI: %s://localhost:%s/api-docs", scheme, config.port)
    logger.info("Content dir: %s", config.content_dir)
    log_seedance_readiness()
    yield
    await close_db()


app = FastAPI(
    title="Manifestia Python POC",
    version="1.0.0",
    description=(
        "Dual-pipeline reel generation: AI video + stock images/videos. "
        "Protected routes under `/api/*` require header `X-API-Key` "
        "(or `Authorization: Bearer <MANIFESTIA_API_KEY>`)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(ApiKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLogMiddleware)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    schema["security"] = [{"ApiKeyAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    field_errors: dict[str, list[str]] = {}
    form_errors: list[str] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        msg = str(error.get("msg") or "Invalid")
        if len(loc) <= 1:
            form_errors.append(msg)
        else:
            key = str(loc[-1])
            field_errors.setdefault(key, []).append(msg)
    logger.warning("validation failed %s %s form=%s fields=%s", request.method, request.url.path, form_errors, field_errors)
    return JSONResponse(
        status_code=400,
        content={"error": "Validation failed", "details": {"formErrors": form_errors, "fieldErrors": field_errors}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("%s %s -> %s %s", request.method, request.url.path, exc.status_code, exc.detail)
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, (HTTPException, RequestValidationError)):
        raise exc
    logger.exception("unhandled error %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": str(exc) if str(exc) else "Internal server error"})


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "ok",
        "byteplusApiKey": "set" if config.byteplus_api_key else "missing",
        "byteplusVideoModel": config.byteplus_video_model,
        "publicApiUrl": config.public_api_url,
        "apiAuth": "required" if config.manifestia_api_key else "disabled",
    }


@app.get("/api-docs", include_in_schema=False)
async def swagger_ui():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Manifestia Python POC")


app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(library_router)
app.include_router(reels_router)
app.include_router(media_router)

config.storage_root.mkdir(parents=True, exist_ok=True)
_music_root = get_music_root()
if _music_root.exists():
    app.mount(MUSIC_URL_PREFIX, StaticFiles(directory=str(_music_root)), name="library-music")
app.mount(MEDIA_URL_PREFIX, StaticFiles(directory=str(config.storage_root)), name="media")
