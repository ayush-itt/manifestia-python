from __future__ import annotations

import json
from typing import Any

from app.storage.paths import to_media_url
from app.types import MusicTrack, ReelRow, SceneRow, SessionRow


def map_scene(row: SceneRow) -> dict[str, Any]:
    try:
        reference_images = json.loads(row.get("reference_images") or "[]")
    except json.JSONDecodeError:
        reference_images = []
    media_path = row.get("media_path")
    return {
        "sceneId": row["scene_id"],
        "reelId": row["reel_id"],
        "sceneIndex": row["scene_index"],
        "title": row.get("title"),
        "prompt": row.get("prompt"),
        "voiceover": row.get("voiceover"),
        "referenceImages": reference_images,
        "mediaType": row.get("media_type"),
        "mediaPath": media_path,
        "mediaUrl": to_media_url(media_path) if media_path else None,
        "durationSec": row.get("duration_sec"),
        "status": row.get("status"),
        "stockQuery": row.get("stock_query"),
        "stockSource": row.get("stock_source"),
        "errorMessage": row.get("error_message"),
        "createdAt": row.get("created_at"),
    }


def map_reel(row: ReelRow, scenes: list[SceneRow] | None = None) -> dict[str, Any]:
    output_path = row.get("output_path")
    payload: dict[str, Any] = {
        "reelId": row["reel_id"],
        "sessionId": row["session_id"],
        "type": row["type"],
        "status": row["status"],
        "outputPath": output_path,
        "outputUrl": to_media_url(output_path) if output_path else None,
        "durationSec": row.get("duration_sec"),
        "musicTrackId": row.get("music_track_id"),
        "createdAt": row.get("created_at"),
        "startedAt": row.get("started_at"),
        "completedAt": row.get("completed_at"),
        "errorMessage": row.get("error_message"),
        "progress": row.get("progress"),
    }
    if scenes is not None:
        payload["scenes"] = [map_scene(s) for s in scenes]
    return payload


def map_session(row: SessionRow) -> dict[str, Any]:
    try:
        answers = json.loads(row.get("onboarding_answers") or "{}")
    except json.JSONDecodeError:
        answers = {}
    return {
        "sessionId": row["session_id"],
        "deviceId": row["device_id"],
        "answers": answers,
        "createdAt": row.get("created_at"),
        "completedAt": row.get("completed_at"),
        "status": row.get("status"),
    }


def map_music_public(track: MusicTrack) -> dict[str, Any]:
    public = dict(track)
    public.pop("absolutePath", None)
    return public
