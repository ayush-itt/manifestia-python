from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.models import get_device, upsert_device
from app.schemas.api import RegisterBody

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register")
async def register(body: RegisterBody | None = None):
    payload = body or RegisterBody()
    device = await upsert_device(payload.deviceId)
    return {
        "deviceId": device["device_id"],
        "token": device["device_id"],
        "createdAt": device["created_at"],
        "lastSeenAt": device["last_seen_at"],
    }


@router.get("/device/{deviceId}")
async def get_device_info(deviceId: str):
    device = await get_device(deviceId)
    if not device:
        raise HTTPException(status_code=404, detail={"error": "Device not found"})
    return {
        "deviceId": device["device_id"],
        "createdAt": device["created_at"],
        "lastSeenAt": device["last_seen_at"],
    }
