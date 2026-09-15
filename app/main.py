from __future__ import annotations

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
from app.routes.auth import router as auth_router
from app.routes.library import router as library_router
from app.routes.media import router as media_router
from app.routes.onboarding import router as onboarding_router
from app.routes.reels import router as reels_router
from app.storage.paths import ensure_storage_root


def log_seedance_readiness() -> None:
    key_status = "set" if config.byteplus_api_key else "MISSING"
    print("[readiness] Seedance pipeline check:", flush=True)
    print(f"  BYTEPLUS_API_KEY: {key_status}", flush=True)
    print(f"  BYTEPLUS_VIDEO_MODEL: {config.byteplus_video_model}", flush=True)
    print(f"  BYTEPLUS_API_URL: {config.byteplus_api_url}", flush=True)
    print(f"  PUBLIC_API_URL: {config.public_api_url}", flush=True)
    if not config.byteplus_api_key:
        print("  Status: INCOMPLETE — BYTEPLUS_API_KEY missing (restart after editing .env)", flush=True)
    else:
        print("  Status: READY for Seedance video generation", flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await get_db()
    await ensure_storage_root()
    print(f"Manifestia Python backend ready on http://localhost:{config.port}", flush=True)
    print(f"Swagger UI: http://localhost:{config.port}/api-docs", flush=True)
    print(f"Content dir: {config.content_dir}", flush=True)
    log_seedance_readiness()
    yield
    await close_db()


app = FastAPI(
    title="Manifestia Python POC",
    version="1.0.0",
    description="Dual-pipeline reel generation: AI video + stock images/videos.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
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
    return JSONResponse(
        status_code=400,
        content={"error": "Validation failed", "details": {"formErrors": form_errors, "fieldErrors": field_errors}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    if isinstance(exc, (HTTPException, RequestValidationError)):
        raise exc
    print(exc)
    return JSONResponse(status_code=500, content={"error": str(exc) if str(exc) else "Internal server error"})


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "ok",
        "byteplusApiKey": "set" if config.byteplus_api_key else "missing",
        "byteplusVideoModel": config.byteplus_video_model,
        "publicApiUrl": config.public_api_url,
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
