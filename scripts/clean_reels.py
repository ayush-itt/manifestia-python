from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from app.config import config
from app.storage.paths import reel_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean generated reel video data (SQLite + storage/sessions)."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--devices", action="store_true")
    parser.add_argument("--session")
    parser.add_argument("--reel")
    args = parser.parse_args()
    if args.session and args.reel:
        parser.error("Use --session or --reel, not both")
    return args


def count(db: sqlite3.Connection, table: str) -> int:
    row = db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row[0])


def remove_dir(path: Path, dry_run: bool) -> bool:
    if dry_run:
        print(f"dry-run rm {path}")
        return True
    if not path.exists():
        return False
    import shutil

    shutil.rmtree(path, ignore_errors=False)
    return True


def clean_all(db: sqlite3.Connection, flags: argparse.Namespace) -> None:
    before = {
        "scenes": count(db, "scenes"),
        "reels": count(db, "reels"),
        "sessions": count(db, "sessions"),
        "devices": count(db, "devices"),
    }
    print("before", before)
    if not flags.dry_run:
        db.execute("BEGIN")
        try:
            db.execute("DELETE FROM scenes")
            db.execute("DELETE FROM reels")
            db.execute("DELETE FROM sessions")
            if flags.devices:
                db.execute("DELETE FROM devices")
            db.commit()
        except Exception:
            db.rollback()
            raise
    remove_dir(config.storage_root / "sessions", flags.dry_run)
    print(
        "after",
        {
            "scenes": before["scenes"] if flags.dry_run else count(db, "scenes"),
            "reels": before["reels"] if flags.dry_run else count(db, "reels"),
            "sessions": before["sessions"] if flags.dry_run else count(db, "sessions"),
            "devices": before["devices"] if flags.dry_run else count(db, "devices"),
        },
    )


def clean_session(db: sqlite3.Connection, session_id: str, dry_run: bool) -> None:
    session = db.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not session:
        raise RuntimeError(f"Session not found: {session_id}")
    reels = db.execute("SELECT reel_id FROM reels WHERE session_id = ?", (session_id,)).fetchall()
    print(f"session {session_id}: {len(reels)} reel(s)")
    if not dry_run:
        db.execute("BEGIN")
        try:
            for reel in reels:
                db.execute("DELETE FROM scenes WHERE reel_id = ?", (reel[0],))
            db.execute("DELETE FROM reels WHERE session_id = ?", (session_id,))
            db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            db.commit()
        except Exception:
            db.rollback()
            raise
    remove_dir(config.storage_root / "sessions" / session_id, dry_run)


def clean_reel(db: sqlite3.Connection, reel_id: str, dry_run: bool) -> None:
    reel = db.execute("SELECT reel_id, session_id FROM reels WHERE reel_id = ?", (reel_id,)).fetchone()
    if not reel:
        raise RuntimeError(f"Reel not found: {reel_id}")
    print(f"reel {reel_id} session {reel[1]}")
    leftover = 1
    if not dry_run:
        db.execute("BEGIN")
        try:
            db.execute("DELETE FROM scenes WHERE reel_id = ?", (reel_id,))
            db.execute("DELETE FROM reels WHERE reel_id = ?", (reel_id,))
            leftover_row = db.execute("SELECT COUNT(*) AS n FROM reels WHERE session_id = ?", (reel[1],)).fetchone()
            leftover = leftover_row[0]
            if leftover == 0:
                db.execute("DELETE FROM sessions WHERE session_id = ?", (reel[1],))
            db.commit()
        except Exception:
            db.rollback()
            raise
    remove_dir(reel_dir(reel[1], reel_id), dry_run)
    leftover = leftover if not dry_run else 1
    if leftover == 0:
        remove_dir(config.storage_root / "sessions" / reel[1], dry_run)


def main() -> None:
    flags = parse_args()
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.database_path)
    try:
        if flags.reel:
            clean_reel(db, flags.reel, flags.dry_run)
        elif flags.session:
            clean_session(db, flags.session, flags.dry_run)
        else:
            clean_all(db, flags)
        print("dry-run complete" if flags.dry_run else "cleaned generated reel data")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        message = str(err)
        print(message, file=sys.stderr)
        if "SQLITE_BUSY" in message or "locked" in message.lower():
            print("Stop the backend and try again.", file=sys.stderr)
        sys.exit(1)
