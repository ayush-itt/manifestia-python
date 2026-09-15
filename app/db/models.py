from __future__ import annotations

import json
import uuid
from functools import wraps
from typing import Any, Callable, TypeVar

from app.db.connection import get_db, now_iso, row_to_dict, write_lock
from app.types import (
    DeviceRow,
    LibraryReelRow,
    ReelRow,
    ReelStatus,
    ReelType,
    SceneRow,
    SceneStatus,
    SessionRow,
    SessionStatus,
)

F = TypeVar("F", bound=Callable[..., Any])


def _locked(fn: F) -> F:
    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any):
        async with write_lock():
            return await fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


@_locked
async def upsert_device(device_id: str | None = None) -> DeviceRow:
    db = await get_db()
    ident = (device_id or "").strip() or str(uuid.uuid4())
    now = now_iso()
    async with db.execute("SELECT * FROM devices WHERE device_id = ?", (ident,)) as cur:
        existing = row_to_dict(await cur.fetchone())
    if existing:
        await db.execute("UPDATE devices SET last_seen_at = ? WHERE device_id = ?", (now, ident))
        await db.commit()
        existing["last_seen_at"] = now
        return existing  # type: ignore[return-value]
    row: DeviceRow = {"device_id": ident, "created_at": now, "last_seen_at": now}
    await db.execute(
        "INSERT INTO devices (device_id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (row["device_id"], row["created_at"], row["last_seen_at"]),
    )
    await db.commit()
    return row


async def get_device(device_id: str) -> DeviceRow | None:
    db = await get_db()
    async with db.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)) as cur:
        return row_to_dict(await cur.fetchone())  # type: ignore[return-value]


@_locked
async def create_session(device_id: str, answers: dict[str, Any]) -> SessionRow:
    db = await get_db()
    row: SessionRow = {
        "session_id": str(uuid.uuid4()),
        "device_id": device_id,
        "onboarding_answers": json.dumps(answers),
        "created_at": now_iso(),
        "completed_at": now_iso(),
        "status": "generating",
    }
    await db.execute(
        """
        INSERT INTO sessions (session_id, device_id, onboarding_answers, created_at, completed_at, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row["session_id"],
            row["device_id"],
            row["onboarding_answers"],
            row["created_at"],
            row["completed_at"],
            row["status"],
        ),
    )
    await db.commit()
    return row


async def get_session(session_id: str) -> SessionRow | None:
    db = await get_db()
    async with db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)) as cur:
        return row_to_dict(await cur.fetchone())  # type: ignore[return-value]


async def list_sessions_for_device(device_id: str) -> list[SessionRow]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM sessions WHERE device_id = ? ORDER BY created_at DESC",
        (device_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


@_locked
async def update_session_status(session_id: str, status: SessionStatus) -> None:
    db = await get_db()
    await db.execute("UPDATE sessions SET status = ? WHERE session_id = ?", (status, session_id))
    await db.commit()


@_locked
async def create_reel(session_id: str, reel_type: ReelType) -> ReelRow:
    db = await get_db()
    row: ReelRow = {
        "reel_id": str(uuid.uuid4()),
        "session_id": session_id,
        "type": reel_type,
        "status": "queued",
        "output_path": None,
        "duration_sec": None,
        "music_track_id": None,
        "created_at": now_iso(),
        "started_at": None,
        "completed_at": None,
        "error_message": None,
        "progress": 0,
    }
    await db.execute(
        """
        INSERT INTO reels (
          reel_id, session_id, type, status, output_path, duration_sec, music_track_id,
          created_at, started_at, completed_at, error_message, progress
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["reel_id"],
            row["session_id"],
            row["type"],
            row["status"],
            row["output_path"],
            row["duration_sec"],
            row["music_track_id"],
            row["created_at"],
            row["started_at"],
            row["completed_at"],
            row["error_message"],
            row["progress"],
        ),
    )
    await db.commit()
    return row


async def get_reel(reel_id: str) -> ReelRow | None:
    db = await get_db()
    async with db.execute("SELECT * FROM reels WHERE reel_id = ?", (reel_id,)) as cur:
        return row_to_dict(await cur.fetchone())  # type: ignore[return-value]


async def list_reels_for_session(session_id: str) -> list[ReelRow]:
    db = await get_db()
    async with db.execute("SELECT * FROM reels WHERE session_id = ?", (session_id,)) as cur:
        rows = await cur.fetchall()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


async def list_library_reels(
    filters: dict[str, str | None],
) -> list[LibraryReelRow]:
    clauses: list[str] = []
    params: list[str] = []
    if filters.get("deviceId"):
        clauses.append("s.device_id = ?")
        params.append(filters["deviceId"] or "")
    if filters.get("type"):
        clauses.append("r.type = ?")
        params.append(filters["type"] or "")
    if filters.get("status"):
        clauses.append("r.status = ?")
        params.append(filters["status"] or "")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    db = await get_db()
    async with db.execute(
        f"""
        SELECT r.*, s.device_id, s.onboarding_answers, s.status AS session_status
        FROM reels r
        JOIN sessions s ON s.session_id = r.session_id
        {where}
        ORDER BY COALESCE(r.completed_at, r.created_at) DESC
        """,
        params,
    ) as cur:
        rows = await cur.fetchall()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


@_locked
async def update_reel(reel_id: str, patch: dict[str, Any]) -> None:
    current = await get_reel(reel_id)
    if not current:
        raise RuntimeError(f"Reel not found: {reel_id}")
    next_row = {**current, **patch}
    db = await get_db()
    await db.execute(
        """
        UPDATE reels SET status = ?, output_path = ?, duration_sec = ?, music_track_id = ?,
          started_at = ?, completed_at = ?, error_message = ?, progress = ?
        WHERE reel_id = ?
        """,
        (
            next_row["status"],
            next_row["output_path"],
            next_row["duration_sec"],
            next_row["music_track_id"],
            next_row["started_at"],
            next_row["completed_at"],
            next_row["error_message"],
            next_row["progress"],
            reel_id,
        ),
    )
    await db.commit()


async def set_reel_status(reel_id: str, status: ReelStatus, extra: dict[str, Any] | None = None) -> None:
    await update_reel(reel_id, {"status": status, **(extra or {})})


@_locked
async def insert_scene(scene: dict[str, Any]) -> SceneRow:
    db = await get_db()
    row: SceneRow = {
        "scene_id": scene["scene_id"],
        "reel_id": scene["reel_id"],
        "scene_index": scene["scene_index"],
        "title": scene.get("title"),
        "prompt": scene.get("prompt"),
        "voiceover": scene.get("voiceover"),
        "reference_images": scene.get("reference_images", "[]"),
        "media_type": scene.get("media_type"),
        "media_path": scene.get("media_path"),
        "duration_sec": scene.get("duration_sec"),
        "status": scene.get("status", "queued"),
        "stock_query": scene.get("stock_query"),
        "stock_source": scene.get("stock_source"),
        "error_message": scene.get("error_message"),
        "created_at": scene.get("created_at") or now_iso(),
    }
    await db.execute(
        """
        INSERT INTO scenes (
          scene_id, reel_id, scene_index, title, prompt, voiceover, reference_images,
          media_type, media_path, duration_sec, status, stock_query, stock_source,
          error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["scene_id"],
            row["reel_id"],
            row["scene_index"],
            row["title"],
            row["prompt"],
            row["voiceover"],
            row["reference_images"],
            row["media_type"],
            row["media_path"],
            row["duration_sec"],
            row["status"],
            row["stock_query"],
            row["stock_source"],
            row["error_message"],
            row["created_at"],
        ),
    )
    await db.commit()
    return row


async def get_scene(scene_id: str) -> SceneRow | None:
    db = await get_db()
    async with db.execute("SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)) as cur:
        return row_to_dict(await cur.fetchone())  # type: ignore[return-value]


async def list_scenes_for_reel(reel_id: str) -> list[SceneRow]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM scenes WHERE reel_id = ? ORDER BY scene_index ASC",
        (reel_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


@_locked
async def update_scene(scene_id: str, patch: dict[str, Any]) -> None:
    current = await get_scene(scene_id)
    if not current:
        raise RuntimeError(f"Scene not found: {scene_id}")
    next_row = {**current, **patch}
    db = await get_db()
    await db.execute(
        """
        UPDATE scenes SET status = ?, media_type = ?, media_path = ?, stock_source = ?,
          error_message = ?, duration_sec = ?
        WHERE scene_id = ?
        """,
        (
            next_row["status"],
            next_row["media_type"],
            next_row["media_path"],
            next_row["stock_source"],
            next_row["error_message"],
            next_row["duration_sec"],
            scene_id,
        ),
    )
    await db.commit()


async def set_scene_status(scene_id: str, status: SceneStatus, extra: dict[str, Any] | None = None) -> None:
    await update_scene(scene_id, {"status": status, **(extra or {})})


@_locked
async def delete_scenes_for_reel(reel_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM scenes WHERE reel_id = ?", (reel_id,))
    await db.commit()
