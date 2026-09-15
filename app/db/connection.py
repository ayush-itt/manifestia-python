from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
  device_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  onboarding_answers TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  FOREIGN KEY (device_id) REFERENCES devices(device_id)
);

CREATE TABLE IF NOT EXISTS reels (
  reel_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  output_path TEXT,
  duration_sec REAL,
  music_track_id TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  error_message TEXT,
  progress INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS scenes (
  scene_id TEXT PRIMARY KEY,
  reel_id TEXT NOT NULL,
  scene_index INTEGER NOT NULL,
  title TEXT,
  prompt TEXT,
  voiceover TEXT,
  reference_images TEXT NOT NULL DEFAULT '[]',
  media_type TEXT,
  media_path TEXT,
  duration_sec REAL DEFAULT 10,
  status TEXT NOT NULL DEFAULT 'queued',
  stock_query TEXT,
  stock_source TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (reel_id) REFERENCES reels(reel_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_device ON sessions(device_id);
CREATE INDEX IF NOT EXISTS idx_reels_session ON reels(session_id);
CREATE INDEX IF NOT EXISTS idx_scenes_reel ON scenes(reel_id, scene_index);
"""

_db: aiosqlite.Connection | None = None
_write_lock = asyncio.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is not None:
        return _db
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(config.database_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA foreign_keys = ON")
    await db.executescript(SCHEMA)
    await db.commit()
    _db = db
    return db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def write_lock() -> asyncio.Lock:
    return _write_lock
