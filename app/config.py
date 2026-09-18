from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_BYTEPLUS_VIDEO_MODEL = "dreamina-seedance-2-0-260128"
DEFAULT_MODELARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"

BACKEND_ROOT = Path(__file__).resolve().parent.parent
POC_ROOT = BACKEND_ROOT
CONTENT_DIR = BACKEND_ROOT / "content"

load_dotenv(BACKEND_ROOT / ".env", override=True)


def byteplus_api_key() -> str:
    return (os.environ.get("BYTEPLUS_API_KEY") or "").strip()

MEDIA_URL_PREFIX = "/media"
MUSIC_URL_PREFIX = "/media/library-music"


def _resolve_path(raw: str | None, fallback: Path) -> Path:
    if raw and raw.strip():
        return Path(raw.strip()).expanduser().resolve()
    return fallback.resolve()


def _resolve_story_path(story_path: str, templates_dir: str) -> Path:
    explicit = story_path.strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    templates = templates_dir.strip()
    if templates:
        path = Path(templates).expanduser().resolve()
        if path.suffix.lower() == ".json":
            return path
        return (path / "story.json").resolve()
    return (CONTENT_DIR / "story" / "story.json").resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    port: int = 4100
    node_env: str = "development"
    cors_origin: str = "http://localhost:5173"
    database_path: str = ""
    storage_root: str = ""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    unsplash_access_key: str = ""
    coverr_api_key: str = ""
    nasa_api_key: str = ""
    byteplus_api_key: str = ""
    byteplus_api_url: str = DEFAULT_MODELARK_BASE_URL
    byteplus_video_model: str = DEFAULT_BYTEPLUS_VIDEO_MODEL
    public_api_url: str = "http://localhost:4100"
    ssl_certfile: str = ""
    ssl_keyfile: str = ""
    story_path: str = ""
    story_templates_dir: str = ""
    story_assets_dir: str = ""
    background_music_dir: str = ""
    onboarding_questions_path: str = ""
    onboarding_catalog_path: str = ""
    video_ratio: str = "9:16"
    video_width: int = 720
    video_height: int = 1280
    video_fps: int = 24
    scene_duration_sec: float = 10
    narration_delay_sec: float = 2
    tts_voice: str = "en-US-AriaNeural"
    # Shared secret for mobile / clients. Prefer env MANIFESTIA_API_KEY.
    manifestia_api_key: str = ""
    log_level: str = "INFO"

    def resolved_database_path(self) -> Path:
        if self.database_path.strip():
            return Path(self.database_path).expanduser().resolve()
        return (BACKEND_ROOT / "storage" / "manifestia.db").resolve()

    def resolved_storage_root(self) -> Path:
        if self.storage_root.strip():
            return Path(self.storage_root).expanduser().resolve()
        return (BACKEND_ROOT / "storage").resolve()

    def resolved_story_path(self) -> Path:
        return _resolve_story_path(self.story_path, self.story_templates_dir)

    def resolved_story_assets_dir(self) -> Path:
        return _resolve_path(self.story_assets_dir, CONTENT_DIR / "story")

    def resolved_background_music_dir(self) -> Path:
        return _resolve_path(self.background_music_dir, CONTENT_DIR / "background-music")

    def resolved_onboarding_questions_path(self) -> Path:
        return _resolve_path(self.onboarding_questions_path, CONTENT_DIR / "onboarding" / "questions.json")

    def resolved_onboarding_catalog_path(self) -> Path:
        return _resolve_path(self.onboarding_catalog_path, CONTENT_DIR / "onboarding" / "catalog.json")


_raw = Settings()


class Config:
    port: int = _raw.port
    cors_origin: str = _raw.cors_origin
    database_path: Path = _raw.resolved_database_path()
    storage_root: Path = _raw.resolved_storage_root()
    pexels_api_key: str = _raw.pexels_api_key
    pixabay_api_key: str = _raw.pixabay_api_key
    unsplash_access_key: str = _raw.unsplash_access_key
    coverr_api_key: str = _raw.coverr_api_key
    nasa_api_key: str = _raw.nasa_api_key
    byteplus_api_url: str = _raw.byteplus_api_url.strip() or DEFAULT_MODELARK_BASE_URL
    byteplus_video_model: str = _raw.byteplus_video_model.strip() or DEFAULT_BYTEPLUS_VIDEO_MODEL
    public_api_url: str = _raw.public_api_url.strip() or "http://localhost:4100"
    ssl_certfile: str = _raw.ssl_certfile.strip()
    ssl_keyfile: str = _raw.ssl_keyfile.strip()
    content_dir: Path = CONTENT_DIR
    story_path: Path = _raw.resolved_story_path()
    story_assets_dir: Path = _raw.resolved_story_assets_dir()
    background_music_dir: Path = _raw.resolved_background_music_dir()
    onboarding_questions_path: Path = _raw.resolved_onboarding_questions_path()
    onboarding_catalog_path: Path = _raw.resolved_onboarding_catalog_path()
    video_ratio: str = _raw.video_ratio if _raw.video_ratio in ("9:16", "16:9") else "9:16"
    video_width: int = _raw.video_width
    video_height: int = _raw.video_height
    video_fps: int = _raw.video_fps
    scene_duration_sec: float = _raw.scene_duration_sec
    narration_delay_sec: float = _raw.narration_delay_sec
    default_edge_voice: str = _raw.tts_voice.strip() or "en-US-AriaNeural"
    poc_root: Path = POC_ROOT
    backend_root: Path = BACKEND_ROOT
    node_env: str = _raw.node_env
    log_level: str = (_raw.log_level or "INFO").strip().upper() or "INFO"

    @property
    def byteplus_api_key(self) -> str:
        return byteplus_api_key()

    @property
    def manifestia_api_key(self) -> str:
        # Allow either name; prefer MANIFESTIA_API_KEY.
        return (
            (_raw.manifestia_api_key or "").strip()
            or (os.environ.get("MANIFESTIA_API_KEY") or "").strip()
            or (os.environ.get("API_KEY") or "").strip()
        )

    def resolved_ssl_files(self) -> tuple[Path, Path] | None:
        cert = self.ssl_certfile
        key = self.ssl_keyfile
        if not cert and not key:
            return None
        if not cert or not key:
            raise ValueError("Set both SSL_CERTFILE and SSL_KEYFILE, or neither.")
        cert_path = Path(cert).expanduser()
        key_path = Path(key).expanduser()
        if not cert_path.is_absolute():
            cert_path = (BACKEND_ROOT / cert_path).resolve()
        else:
            cert_path = cert_path.resolve()
        if not key_path.is_absolute():
            key_path = (BACKEND_ROOT / key_path).resolve()
        else:
            key_path = key_path.resolve()
        if not cert_path.is_file() or not key_path.is_file():
            raise FileNotFoundError(
                f"SSL files not found. cert={cert_path} key={key_path}. "
                "Run: python -m scripts.gen_dev_ssl"
            )
        return cert_path, key_path


config = Config()
