from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import MUSIC_URL_PREFIX, config
from app.types import MusicTrack

_cache: dict[str, Any] | None = None


def parse_duration_label(label: str | None) -> float:
    if not label:
        return 0
    parts = [Number(p) for p in label.split(":")]
    if any(n is None for n in parts):
        return 0
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def Number(value: str) -> float | None:
    try:
        n = float(value)
    except ValueError:
        return None
    return n if n == n else None  # NaN check


async def _collect_category_files(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.exists():
        return found
    for path in root.rglob("category.json"):
        if path.is_file():
            found.append(path)
    return found


async def _signature_for(files: list[Path]) -> str:
    stamps: list[str] = []
    for file in sorted(files, key=lambda p: str(p)):
        try:
            info = file.stat()
            stamps.append(f"{file}:{info.st_mtime_ns / 1_000_000}:{info.st_size}")
        except OSError:
            stamps.append(f"{file}:missing")
    return "|".join(stamps)


def _to_url(absolute_path: Path) -> str:
    rel = absolute_path.resolve().relative_to(config.background_music_dir.resolve()).as_posix()
    return f"{MUSIC_URL_PREFIX}/{rel}"


async def _load_tracks(files: list[Path]) -> list[MusicTrack]:
    by_id: dict[str, MusicTrack] = {}
    for file in files:
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        mood = ((raw.get("subCategory") or {}).get("slug") or (raw.get("category") or {}).get("slug") or "mood")
        category_dir = file.parent
        for item in raw.get("musics") or []:
            audio = item.get("audio") or {}
            relative_file = str(audio.get("file") or "").lstrip("./")
            item_id = item.get("id")
            if not relative_file or not item_id:
                continue
            absolute_path = category_dir / relative_file
            tags = [t.strip() for t in (item.get("tags") or []) if str(t).strip()]
            existing = by_id.get(item_id)
            if existing:
                merged = set(existing["tags"]) | set(tags)
                existing["tags"] = list(merged)
                if mood != "mood" and existing["mood"] == "mood":
                    existing["mood"] = mood
                continue
            by_id[item_id] = {
                "id": item_id,
                "title": item.get("title") or "",
                "mood": mood,
                "tags": tags,
                "durationSec": parse_duration_label(item.get("duration")),
                "durationLabel": item.get("duration") or "00:00",
                "fileName": audio.get("fileName") or relative_file,
                "absolutePath": str(absolute_path),
                "fileUrl": _to_url(absolute_path),
            }
    return list(by_id.values())


async def get_music_catalog() -> list[MusicTrack]:
    global _cache
    files = await _collect_category_files(config.background_music_dir)
    signature = await _signature_for(files)
    if _cache and _cache.get("signature") == signature:
        return _cache["tracks"]
    tracks = await _load_tracks(files)
    _cache = {"tracks": tracks, "signature": signature}
    return tracks


async def list_music_moods() -> list[str]:
    tracks = await get_music_catalog()
    return sorted({t["mood"] for t in tracks})


def get_music_root() -> Path:
    return config.background_music_dir
