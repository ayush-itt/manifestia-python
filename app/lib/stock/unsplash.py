from __future__ import annotations

import httpx

from app.config import config
from app.lib.stock.pexels import StockSearchInput
from app.types import StockCandidate

LICENSE = "Unsplash License"


def unsplash_available() -> bool:
    return bool(config.unsplash_access_key)


async def search_unsplash(input: StockSearchInput) -> list[StockCandidate]:
    if not unsplash_available():
        return []
    if input.get("kind") == "video":
        return []
    params = {
        "query": input["query"],
        "page": str(input.get("page") or 1),
        "per_page": str(max(1, min(input.get("perPage") or 8, 30))),
        "content_filter": "high",
    }
    orientation = input.get("orientation")
    if orientation in ("landscape", "portrait", "square"):
        params["orientation"] = orientation
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(
            "https://api.unsplash.com/search/photos",
            params=params,
            headers={"Authorization": f"Client-ID {config.unsplash_access_key}"},
        )
    if res.status_code >= 400:
        raise RuntimeError(f"Unsplash search failed: {res.status_code}")
    data = res.json()
    out: list[StockCandidate] = []
    for photo in data.get("results") or []:
        urls = photo.get("urls") or {}
        links = photo.get("links") or {}
        user = ((photo.get("user") or {}).get("name")) or ""
        ident = str(photo.get("id") or "")
        hotlink = urls.get("regular") or urls.get("full") or urls.get("raw") or ""
        if not ident or not hotlink:
            continue
        tags = [t.get("title") or "" for t in (photo.get("tags") or []) if t.get("title")]
        candidate: StockCandidate = {
            "id": f"unsplash-{ident}",
            "source": "unsplash",
            "sourceId": ident,
            "sourceUrl": str(links.get("html") or photo.get("links") or ""),
            "downloadUrl": hotlink,
            "previewUrl": urls.get("small") or urls.get("thumb") or hotlink,
            "kind": "image",
            "width": int(photo.get("width") or 0),
            "height": int(photo.get("height") or 0),
            "creator": user,
            "license": LICENSE,
            "tags": tags,
            "previewOnly": False,
            "extra": {
                "downloadLocation": links.get("download_location") or "",
                "photographer": user,
            },
        }
        out.append(candidate)
    return out
