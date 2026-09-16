from __future__ import annotations

from pathlib import Path

from app.config import MEDIA_URL_PREFIX, config


def session_dir(session_id: str) -> Path:
    return config.storage_root / "sessions" / session_id


def reel_dir(session_id: str, reel_id: str) -> Path:
    return session_dir(session_id) / "reels" / reel_id


def scene_dir(session_id: str, reel_id: str, scene_id: str) -> Path:
    return reel_dir(session_id, reel_id) / "scenes" / scene_id


def stock_dest_dir(session_id: str, reel_id: str, scene_id: str) -> Path:
    return scene_dir(session_id, reel_id, scene_id) / "stock"


def scene_video_path(session_id: str, reel_id: str, scene_id: str) -> Path:
    return scene_dir(session_id, reel_id, scene_id) / "video.mp4"


def final_render_path(session_id: str, reel_id: str) -> Path:
    return reel_dir(session_id, reel_id) / "final.mp4"


async def ensure_storage_root() -> None:
    config.storage_root.mkdir(parents=True, exist_ok=True)
    (config.storage_root / "sessions").mkdir(parents=True, exist_ok=True)


async def ensure_reel_dirs(session_id: str, reel_id: str) -> None:
    root = reel_dir(session_id, reel_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "work").mkdir(parents=True, exist_ok=True)
    (root / "scenes").mkdir(parents=True, exist_ok=True)


def to_media_url(absolute_path: str | Path) -> str:
    abs_path = Path(absolute_path).resolve()
    rel = abs_path.relative_to(config.storage_root.resolve()).as_posix()
    return f"{MEDIA_URL_PREFIX}/{rel}"
