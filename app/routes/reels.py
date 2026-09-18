from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.db.models import get_reel, list_scenes_for_reel
from app.mappers import map_reel, map_scene
from app.services.orchestrator import regenerate_reel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reels", tags=["Reels"])


@router.get("/{reelId}")
async def get_reel_detail(reelId: str):
    reel = await get_reel(reelId)
    if not reel:
        raise HTTPException(status_code=404, detail={"error": "Reel not found"})
    return map_reel(reel, await list_scenes_for_reel(reel["reel_id"]))


@router.get("/{reelId}/scenes")
async def get_reel_scenes(reelId: str):
    reel = await get_reel(reelId)
    if not reel:
        raise HTTPException(status_code=404, detail={"error": "Reel not found"})
    return {"scenes": [map_scene(s) for s in await list_scenes_for_reel(reel["reel_id"])]}


@router.get("/{reelId}/download")
async def download_reel(reelId: str):
    reel = await get_reel(reelId)
    if not reel:
        raise HTTPException(status_code=404, detail={"error": "Reel not found"})
    if not reel.get("output_path") or reel.get("status") != "completed":
        raise HTTPException(status_code=409, detail={"error": "Reel is not ready to download"})
    logger.info("download reel=%s type=%s", reelId, reel.get("type"))
    return FileResponse(
        reel["output_path"],
        media_type="video/mp4",
        filename=f"{reel['type']}-{reel['reel_id']}.mp4",
    )


@router.post("/{reelId}/regenerate")
async def regenerate(reelId: str):
    reel = await get_reel(reelId)
    if not reel:
        raise HTTPException(status_code=404, detail={"error": "Reel not found"})
    await regenerate_reel(reel["reel_id"])
    logger.info("regenerate requested reel=%s", reelId)
    updated = await get_reel(reel["reel_id"])
    return map_reel(updated, await list_scenes_for_reel(reel["reel_id"]))  # type: ignore[arg-type]
