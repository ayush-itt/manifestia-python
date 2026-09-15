from __future__ import annotations

from typing import Any, Callable, Literal

import httpx

DEFAULT_MODELARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"

TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "expired"]


class ModelArkError(Exception):
    def __init__(self, message: str, status: int, body: Any):
        super().__init__(message)
        self.status = status
        self.body = body
        self.name = "ModelArkError"


class ModelArkClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_MODELARK_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def _request(self, method: str, path: str, body: Any | None = None) -> Any:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.request(
                method,
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        text = res.text
        parsed = res.json() if text else None
        if res.status_code >= 400:
            err = parsed if isinstance(parsed, dict) else {}
            message = ((err.get("error") or {}).get("message")) or f"ModelArk HTTP {res.status_code}"
            raise ModelArkError(message, res.status_code, parsed)
        return parsed

    async def create_video_task(self, req: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/contents/generations/tasks", req)

    async def get_video_task(self, task_id: str) -> dict[str, Any]:
        from urllib.parse import quote

        return await self._request("GET", f"/contents/generations/tasks/{quote(task_id, safe='')}")

    async def poll_task(
        self,
        task_id: str,
        interval_ms: int = 3500,
        timeout_ms: int = 10 * 60 * 1000,
        on_update: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        import asyncio
        import time

        start = time.monotonic()
        while True:
            task = await self.get_video_task(task_id)
            if on_update:
                on_update(task)
            if task.get("status") in ("succeeded", "failed", "cancelled", "expired"):
                return task
            if (time.monotonic() - start) * 1000 > timeout_ms:
                raise RuntimeError("Timed out waiting for Seedance video task")
            await asyncio.sleep(interval_ms / 1000)


def extract_video_url(task: dict[str, Any]) -> str | None:
    content = task.get("content") or {}
    if content.get("video_url"):
        return content["video_url"]
    for seg in content.get("segments") or []:
        if seg.get("video_url"):
            return seg["video_url"]
    return None
