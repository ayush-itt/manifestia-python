from __future__ import annotations

from typing import TypedDict

import httpx

from app.config import config
from app.types import StockCandidate

LICENSE = "Pexels License (free, no attribution required)"


class StockSearchInput(TypedDict, total=False):
    query: str
    kind: str
    perPage: int
    page: int
    orientation: str
    sources: list[str]
    videoFirst: bool


def pexels_available() -> bool:
    return bool(config.pexels_api_key)


def _pick_mp4(video_files: list[dict]) -> dict | None:
    mp4s = [
        f
        for f in video_files
        if "mp4" in str(f.get("file_type") or "") or ".mp4" in str(f.get("link") or "")
    ]
    if not mp4s:
        return None

    def rank_key(item: dict) -> tuple[int, int]:
        width = int(item.get("width") or 0)
        over = width - 1920 if width > 1920 else 0
        return (over, -width)

    ranked = sorted(mp4s, key=rank_key)
    best = ranked[0] if ranked else None
    if not best or not best.get("link"):
        return None
    return {"url": best["link"], "width": int(best.get("width") or 0)}


async def search_pexels(input: StockSearchInput) -> list[StockCandidate]:
    if not pexels_available():
        return []
    kind = input.get("kind") or "any"
    per_page = max(1, min(input.get("perPage") or 8, 40))
    out: list[StockCandidate] = []
    if kind in ("video", "any"):
        out.extend(await _search_pexels_videos(input["query"], per_page, input.get("page") or 1, input.get("orientation")))
    if kind in ("image", "any"):
        out.extend(await _search_pexels_images(input["query"], per_page, input.get("page") or 1, input.get("orientation")))
    return out


async def _search_pexels_videos(query: str, per_page: int, page: int, orientation: str | None) -> list[StockCandidate]:
    params = {"query": query, "per_page": str(per_page), "page": str(page)}
    if orientation:
        params["orientation"] = orientation
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(
            "https://api.pexels.com/videos/search",
            params=params,
            headers={"Authorization": config.pexels_api_key},
        )
    if res.status_code >= 400:
        raise RuntimeError(f"Pexels video search failed: {res.status_code}")
    data = res.json()
    out: list[StockCandidate] = []
    for video in data.get("videos") or []:
        rend = _pick_mp4(video.get("video_files") or [])
        if not rend:
            continue
        ident = str(video.get("id"))
        user = ((video.get("user") or {}).get("name")) or ""
        duration = float(video.get("duration") or 0) or None
        candidate: StockCandidate = {
            "id": f"pexels-video-{ident}",
            "source": "pexels",
            "sourceId": ident,
            "sourceUrl": str(video.get("url") or ""),
            "downloadUrl": rend["url"],
            "previewUrl": str(video.get("image") or ""),
            "kind": "video",
            "width": int(video.get("width") or rend["width"] or 0),
            "height": int(video.get("height") or 0),
            "creator": user,
            "license": LICENSE,
            "tags": [],
            "previewOnly": False,
        }
        if duration:
            candidate["durationSec"] = duration
        out.append(candidate)
    return out


async def _search_pexels_images(query: str, per_page: int, page: int, orientation: str | None) -> list[StockCandidate]:
    params = {"query": query, "per_page": str(per_page), "page": str(page)}
    if orientation:
        params["orientation"] = orientation
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(
            "https://api.pexels.com/v1/search",
            params=params,
            headers={"Authorization": config.pexels_api_key},
        )
    if res.status_code >= 400:
        raise RuntimeError(f"Pexels image search failed: {res.status_code}")
    data = res.json()
    out: list[StockCandidate] = []
    for photo in data.get("photos") or []:
        src = photo.get("src") or {}
        download_url = src.get("large2x") or src.get("large") or src.get("original") or ""
        if not download_url:
            continue
        ident = str(photo.get("id"))
        out.append(
            {
                "id": f"pexels-image-{ident}",
                "source": "pexels",
                "sourceId": ident,
                "sourceUrl": str(photo.get("url") or ""),
                "downloadUrl": download_url,
                "previewUrl": src.get("medium") or src.get("small") or download_url,
                "kind": "image",
                "width": int(photo.get("width") or 0),
                "height": int(photo.get("height") or 0),
                "creator": str(photo.get("photographer") or ""),
                "license": LICENSE,
                "tags": [],
                "previewOnly": False,
            }
        )
    return out
