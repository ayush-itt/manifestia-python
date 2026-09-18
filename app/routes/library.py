from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Query

from app.db.models import list_library_reels, list_scenes_for_reel
from app.mappers import map_reel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/library", tags=["Library"])


@router.get("")
async def list_library(
    deviceId: str | None = Query(default=None),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    x_device_id: str | None = Header(default=None, alias="x-device-id"),
):
    ident = (deviceId or x_device_id or "").strip() or None
    if type and type not in ("ai_video", "stock_media", "images_only"):
        raise HTTPException(status_code=400, detail={"error": "type must be ai_video, stock_media, or images_only"})
    rows = await list_library_reels({"deviceId": ident, "type": type, "status": status})
    items = []
    for row in rows:
        scenes = await list_scenes_for_reel(row["reel_id"])
        reel = map_reel(row, scenes)
        try:
            answers = json.loads(row.get("onboarding_answers") or "{}")
        except json.JSONDecodeError:
            answers = {}
        preview = reel.get("outputUrl")
        if not preview:
            preview = next((s.get("mediaUrl") for s in (reel.get("scenes") or []) if s.get("mediaUrl")), None)
        items.append(
            {
                **reel,
                "deviceId": row["device_id"],
                "sessionStatus": row["session_status"],
                "name": answers.get("name") if isinstance(answers.get("name"), str) else None,
                "answers": answers,
                "previewUrl": preview,
            }
        )
    logger.info("list device=%s type=%s status=%s count=%s", ident, type, status, len(items))
    return {"count": len(items), "items": items}
