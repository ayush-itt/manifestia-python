from __future__ import annotations

import httpx

from app.config import config
from app.lib.stock.pexels import StockSearchInput
from app.types import StockCandidate

LICENSE = "Coverr License (free for commercial and personal use, no attribution required)"


def coverr_available() -> bool:
    return True


async def search_coverr(input: StockSearchInput) -> list[StockCandidate]:
    if input.get("kind") == "image":
        return []
    params = {
        "query": input["query"],
        "page_size": str(max(1, min(input.get("perPage") or 8, 25))),
        "page": str(input.get("page") or 1),
    }
    headers: dict[str, str] = {}
    if config.coverr_api_key:
        headers["Authorization"] = f"Bearer {config.coverr_api_key}"
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get("https://api.coverr.co/videos", params=params, headers=headers)
    if res.status_code >= 400:
        raise RuntimeError(f"Coverr search failed: {res.status_code}")
    data = res.json()
    hits = data.get("hits") or data.get("videos") or []
    out: list[StockCandidate] = []
    for video in hits:
        ident = str(video.get("id") or video.get("_id") or "")
        urls = video.get("urls") or {}
        download_url = str(video.get("mp4") or video.get("video_url") or urls.get("mp4") or "")
        if not ident or not download_url:
            continue
        duration = float(video.get("duration") or 0) or None
        tags = video.get("tags") if isinstance(video.get("tags"), list) else []
        candidate: StockCandidate = {
            "id": f"coverr-{ident}",
            "source": "coverr",
            "sourceId": ident,
            "sourceUrl": str(video.get("page_url") or video.get("url") or ""),
            "downloadUrl": download_url,
            "previewUrl": str(video.get("thumbnail") or video.get("poster") or ""),
            "kind": "video",
            "width": int(video.get("width") or 1920),
            "height": int(video.get("height") or 1080),
            "creator": str(video.get("author") or "Coverr"),
            "license": LICENSE,
            "tags": [str(t) for t in tags],
            "previewOnly": False,
        }
        if duration:
            candidate["durationSec"] = duration
        out.append(candidate)
    return out
