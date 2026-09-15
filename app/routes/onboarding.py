from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Query

from app.config import config
from app.db.models import (
    create_session,
    get_session,
    list_reels_for_session,
    list_scenes_for_reel,
    list_sessions_for_device,
    upsert_device,
)
from app.mappers import map_reel, map_session
from app.schemas.api import OnboardingSubmit
from app.services.orchestrator import start_both_reels

router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])
UNUSED_IN_POC = {"identity_statement", "limiting_belief"}


@router.get("/questions")
async def questions():
    questions_doc = json.loads(config.onboarding_questions_path.read_text(encoding="utf-8"))
    catalogs = json.loads(config.onboarding_catalog_path.read_text(encoding="utf-8"))
    filtered = [q for q in (questions_doc.get("questions") or []) if q.get("id") not in UNUSED_IN_POC]
    return {**questions_doc, "questions": filtered, "catalogs": catalogs}


@router.post("/submit", status_code=201)
async def submit(body: OnboardingSubmit):
    await upsert_device(body.deviceId)
    session = await create_session(body.deviceId, body.answers)
    ids = await start_both_reels(session["session_id"])
    return {
        "session": map_session(session),
        "reelIds": {"ai": ids.get("aiReelId"), "stock": ids.get("stockReelId"), "images": ids.get("imagesReelId")},
    }


@router.get("/sessions/{sessionId}")
async def get_session_detail(sessionId: str):
    session = await get_session(sessionId)
    if not session:
        raise HTTPException(status_code=404, detail={"error": "Session not found"})
    reels = []
    for reel in await list_reels_for_session(session["session_id"]):
        reels.append(map_reel(reel, await list_scenes_for_reel(reel["reel_id"])))
    return {"session": map_session(session), "reels": reels}


@router.get("/sessions")
async def list_sessions(
    deviceId: str | None = Query(default=None),
    x_device_id: str | None = Header(default=None, alias="x-device-id"),
):
    ident = deviceId or x_device_id or ""
    if not ident:
        raise HTTPException(status_code=400, detail={"error": "deviceId is required"})
    sessions = []
    for session in await list_sessions_for_device(ident):
        mapped = map_session(session)
        mapped["reels"] = [map_reel(r) for r in await list_reels_for_session(session["session_id"])]
        sessions.append(mapped)
    return {"sessions": sessions}
