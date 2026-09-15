from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import urlparse

from app.config import config
from app.storage.paths import to_media_url

IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}


def is_local_public_base(public_base_url: str) -> bool:
    try:
        host = urlparse(public_base_url).hostname or ""
        return host in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return True


def is_inside_storage_root(local_path: str | Path) -> bool:
    abs_path = Path(local_path).resolve()
    try:
        rel = abs_path.relative_to(config.storage_root.resolve())
        return str(rel) != "."
    except ValueError:
        return False


def _to_data_url(local_path: Path, mime_map: dict[str, str], fallback: str) -> str:
    mime = mime_map.get(local_path.suffix.lower(), fallback)
    buf = local_path.read_bytes()
    encoded = base64.b64encode(buf).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _resolve_media_url(local_path: str | Path, public_base_url: str, mime_map: dict[str, str], fallback_mime: str) -> str:
    path = Path(local_path)
    if is_local_public_base(public_base_url) or not is_inside_storage_root(path):
        return _to_data_url(path, mime_map, fallback_mime)
    media_path = to_media_url(path)
    if media_path.startswith("http"):
        return media_path
    return f"{public_base_url.rstrip('/')}{media_path}"


async def resolve_image_url_for_seedance(local_path: str | Path, public_base_url: str) -> str:
    return _resolve_media_url(local_path, public_base_url, IMAGE_MIME, "image/jpeg")


async def resolve_video_url_for_seedance(local_path: str | Path, public_base_url: str) -> str:
    return _resolve_media_url(local_path, public_base_url, VIDEO_MIME, "video/mp4")


def is_local_public_api_url(public_base_url: str) -> bool:
    return is_local_public_base(public_base_url)
