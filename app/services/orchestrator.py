from __future__ import annotations

import asyncio
import json
import logging

from app.db.connection import now_iso
from app.db.models import (
    create_reel,
    delete_scenes_for_reel,
    get_reel,
    get_session,
    list_reels_for_session,
    set_reel_status,
    update_session_status,
)
from app.services.ai_video import generate_ai_video_reel
from app.services.stock_reel import generate_stock_media_reel
from app.types import ReelType

logger = logging.getLogger(__name__)

_running: set[str] = set()
_bg_tasks: set[asyncio.Task] = set()


async def start_both_reels(session_id: str) -> dict[str, str | None]:
    session = await get_session(session_id)
    if not session:
        raise RuntimeError("Session not found")
    try:
        answers = json.loads(session.get("onboarding_answers") or "{}")
    except json.JSONDecodeError:
        answers = {}
    variants = answers.get("reel_variants") if isinstance(answers.get("reel_variants"), list) else ["ai_video", "mixed"]
    want_ai = "ai_video" in variants or len(variants) == 0
    want_mixed = "mixed" in variants or len(variants) == 0
    want_images = "images_only" in variants

    result: dict[str, str | None] = {}
    if want_ai:
        ai = await create_reel(session_id, "ai_video")
        result["aiReelId"] = ai["reel_id"]
        _spawn(run_pipeline(session_id, ai["reel_id"], "ai_video"))
    if want_mixed:
        stock = await create_reel(session_id, "stock_media")
        result["stockReelId"] = stock["reel_id"]
        _spawn(run_pipeline(session_id, stock["reel_id"], "stock_media"))
    if want_images:
        images = await create_reel(session_id, "images_only")
        result["imagesReelId"] = images["reel_id"]
        _spawn(run_pipeline(session_id, images["reel_id"], "images_only"))
    logger.info("started reels session=%s ai=%s mixed=%s images=%s", session_id, result.get("aiReelId"), result.get("stockReelId"), result.get("imagesReelId"))
    return result


async def regenerate_reel(reel_id: str) -> None:
    reel = await get_reel(reel_id)
    if not reel:
        raise RuntimeError("Reel not found")
    await delete_scenes_for_reel(reel_id)
    await set_reel_status(
        reel_id,
        "queued",
        {"error_message": None, "progress": 0, "output_path": None, "completed_at": None},
    )
    logger.info("regenerate reel=%s session=%s type=%s", reel_id, reel["session_id"], reel["type"])
    _spawn(run_pipeline(reel["session_id"], reel_id, reel["type"]))


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def run_pipeline(session_id: str, reel_id: str, reel_type: ReelType) -> None:
    if reel_id in _running:
        logger.info("pipeline skip reel=%s already running", reel_id)
        return
    _running.add(reel_id)
    logger.info("pipeline start reel=%s session=%s type=%s", reel_id, session_id, reel_type)
    try:
        if reel_type == "ai_video":
            await generate_ai_video_reel(session_id, reel_id)
        else:
            await generate_stock_media_reel(session_id, reel_id, "images_only" if reel_type == "images_only" else "mixed")
        logger.info("pipeline complete reel=%s type=%s", reel_id, reel_type)
    except Exception as err:
        msg = str(err) if str(err) else "Generation failed"
        logger.exception("pipeline failed reel=%s type=%s: %s", reel_id, reel_type, msg)
        await set_reel_status(reel_id, "failed", {"error_message": msg, "completed_at": now_iso()})
    finally:
        _running.discard(reel_id)
        await sync_session_status(session_id)


async def sync_session_status(session_id: str) -> None:
    reels = await list_reels_for_session(session_id)
    if any(r["status"] in ("generating", "queued") for r in reels):
        await update_session_status(session_id, "generating")
        logger.info("session status session=%s generating", session_id)
        return
    if reels and all(r["status"] == "completed" for r in reels):
        await update_session_status(session_id, "completed")
        logger.info("session status session=%s completed", session_id)
        return
    if any(r["status"] == "failed" for r in reels):
        await update_session_status(session_id, "failed")
        logger.info("session status session=%s failed", session_id)
