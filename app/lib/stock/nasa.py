from __future__ import annotations

import re

import httpx

from app.config import config
from app.lib.stock.pexels import StockSearchInput
from app.types import StockCandidate

LICENSE = "NASA Media Usage Guidelines (public domain with partner-material caveats)"


def nasa_available() -> bool:
    return True


async def search_nasa(input: StockSearchInput) -> list[StockCandidate]:
    kind_in = input.get("kind")
    media_type = "image" if kind_in == "image" else "video" if kind_in == "video" else "image,video"
    params = {
        "q": input["query"],
        "media_type": media_type,
        "page": str(input.get("page") or 1),
        "page_size": str(max(1, min(input.get("perPage") or 8, 20))),
    }
    if config.nasa_api_key:
        params["api_key"] = config.nasa_api_key
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get("https://images-api.nasa.gov/search", params=params)
        if res.status_code >= 400:
            raise RuntimeError(f"NASA search failed: {res.status_code}")
        data = res.json()
        items = ((data.get("collection") or {}).get("items")) or []
        out: list[StockCandidate] = []
        for item in items[: input.get("perPage") or 8]:
            meta = (item.get("data") or [{}])[0] or {}
            nasa_id = str(meta.get("nasa_id") or "")
            media = str(meta.get("media_type") or "image")
            if not nasa_id or not item.get("href"):
                continue
            kind = "video" if media == "video" else "image"
            preview = ""
            for link in item.get("links") or []:
                if link.get("rel") == "preview":
                    preview = link.get("href") or ""
                    break
            download_url = preview
            try:
                assets_res = await client.get(item["href"], timeout=20)
                if assets_res.status_code < 400:
                    assets = assets_res.json()
                    if isinstance(assets, list):
                        if kind == "video":
                            preferred = next((a for a in assets if re.search(r"\.mp4($|\?)", a, re.I)), None)
                        else:
                            preferred = next(
                                (a for a in assets if re.search(r"\.(jpg|jpeg|png)($|\?)", a, re.I) and not re.search(r"thumb", a, re.I)),
                                None,
                            )
                        download_url = preferred or (assets[0] if assets else preview)
            except Exception:
                pass
            if not download_url:
                continue
            keywords = meta.get("keywords") if isinstance(meta.get("keywords"), list) else []
            out.append(
                {
                    "id": f"nasa-{nasa_id}",
                    "source": "nasa",
                    "sourceId": nasa_id,
                    "sourceUrl": f"https://images.nasa.gov/details-{nasa_id}",
                    "downloadUrl": download_url,
                    "previewUrl": preview or download_url,
                    "kind": kind,
                    "width": 0,
                    "height": 0,
                    "creator": str(meta.get("photographer") or meta.get("center") or "NASA"),
                    "license": LICENSE,
                    "tags": [str(t) for t in keywords],
                    "previewOnly": False,
                }
            )
    return out
