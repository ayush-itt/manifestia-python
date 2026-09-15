from __future__ import annotations

import httpx

from app.config import config
from app.lib.stock.pexels import StockSearchInput
from app.types import StockCandidate

VIDEO_LICENSE = "Pixabay Content License (free, no attribution required)"
IMAGE_LICENSE = VIDEO_LICENSE


def pixabay_available() -> bool:
    return bool(config.pixabay_api_key)


def _pick_video_rendition(videos: dict) -> dict | None:
    for key in ("large", "medium", "small", "tiny"):
        rend = videos.get(key) or {}
        if rend.get("url"):
            return {"url": rend["url"], "width": int(rend.get("width") or 0), "height": int(rend.get("height") or 0)}
    return None


async def search_pixabay(input: StockSearchInput) -> list[StockCandidate]:
    if not pixabay_available():
        return []
    kind = input.get("kind") or "any"
    out: list[StockCandidate] = []
    if kind in ("video", "any"):
        out.extend(await _search_pixabay_videos(input))
    if kind in ("image", "any"):
        out.extend(await _search_pixabay_images(input))
    return out


async def _search_pixabay_videos(input: StockSearchInput) -> list[StockCandidate]:
    params = {
        "key": config.pixabay_api_key,
        "q": input["query"],
        "per_page": str(max(3, min(input.get("perPage") or 8, 50))),
        "page": str(input.get("page") or 1),
        "safesearch": "true",
    }
    if input.get("orientation") == "landscape":
        params["orientation"] = "horizontal"
    if input.get("orientation") == "portrait":
        params["orientation"] = "vertical"
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get("https://pixabay.com/api/videos/", params=params)
    if res.status_code >= 400:
        raise RuntimeError(f"Pixabay video search failed: {res.status_code}")
    data = res.json()
    out: list[StockCandidate] = []
    for hit in data.get("hits") or []:
        videos = hit.get("videos") or {}
        rend = _pick_video_rendition(videos)
        if not rend:
            continue
        ident = str(hit.get("id"))
        tags = [t.strip() for t in str(hit.get("tags") or "").split(",") if t.strip()]
        duration = float(hit.get("duration") or 0) or None
        candidate: StockCandidate = {
            "id": f"pixabay-video-{ident}",
            "source": "pixabay",
            "sourceId": ident,
            "sourceUrl": str(hit.get("pageURL") or ""),
            "downloadUrl": rend["url"],
            "previewUrl": str(hit.get("userImageURL") or (videos.get("tiny") or {}).get("url") or ""),
            "kind": "video",
            "width": rend["width"],
            "height": rend["height"],
            "creator": str(hit.get("user") or ""),
            "license": VIDEO_LICENSE,
            "tags": tags,
            "previewOnly": False,
        }
        if duration:
            candidate["durationSec"] = duration
        out.append(candidate)
    return out


async def _search_pixabay_images(input: StockSearchInput) -> list[StockCandidate]:
    params = {
        "key": config.pixabay_api_key,
        "q": input["query"],
        "per_page": str(max(3, min(input.get("perPage") or 8, 50))),
        "page": str(input.get("page") or 1),
        "safesearch": "true",
        "image_type": "photo",
    }
    if input.get("orientation") == "landscape":
        params["orientation"] = "horizontal"
    if input.get("orientation") == "portrait":
        params["orientation"] = "vertical"
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get("https://pixabay.com/api/", params=params)
    if res.status_code >= 400:
        raise RuntimeError(f"Pixabay image search failed: {res.status_code}")
    data = res.json()
    out: list[StockCandidate] = []
    for hit in data.get("hits") or []:
        download_url = str(hit.get("largeImageURL") or hit.get("webformatURL") or "")
        if not download_url:
            continue
        ident = str(hit.get("id"))
        tags = [t.strip() for t in str(hit.get("tags") or "").split(",") if t.strip()]
        out.append(
            {
                "id": f"pixabay-image-{ident}",
                "source": "pixabay",
                "sourceId": ident,
                "sourceUrl": str(hit.get("pageURL") or ""),
                "downloadUrl": download_url,
                "previewUrl": str(hit.get("previewURL") or download_url),
                "kind": "image",
                "width": int(hit.get("imageWidth") or hit.get("webformatWidth") or 0),
                "height": int(hit.get("imageHeight") or hit.get("webformatHeight") or 0),
                "creator": str(hit.get("user") or ""),
                "license": IMAGE_LICENSE,
                "tags": tags,
                "previewOnly": False,
            }
        )
    return out
