from __future__ import annotations

import asyncio
from pathlib import Path

from app.lib.stock.coverr import coverr_available, search_coverr
from app.lib.stock.download import download_url_to_file, stock_file_extension
from app.lib.stock.nasa import nasa_available, search_nasa
from app.lib.stock.pexels import StockSearchInput, pexels_available, search_pexels
from app.lib.stock.pixabay import pixabay_available, search_pixabay
from app.lib.stock.unsplash import search_unsplash, unsplash_available
from app.types import DownloadedStock, StockCandidate, StockSourceId

DEFAULT_BAKE_SOURCES: list[StockSourceId] = ["pexels", "pixabay", "unsplash", "coverr"]


def stock_source_status() -> dict[str, dict[str, object]]:
    return {
        "pexels": {
            "available": pexels_available(),
            "bakeable": True,
            "notes": "Images + video. Commercial, no attribution, no watermark.",
        },
        "pixabay": {
            "available": pixabay_available(),
            "bakeable": True,
            "notes": "Images + video. Commercial, no attribution, no watermark.",
        },
        "unsplash": {
            "available": unsplash_available(),
            "bakeable": True,
            "notes": "Images only. Downloaded into the MP4 like Manifest.",
        },
        "coverr": {
            "available": coverr_available(),
            "bakeable": True,
            "notes": "Cinematic stock video. Optional COVERR_API_KEY for higher limits.",
        },
        "nasa": {
            "available": nasa_available(),
            "bakeable": True,
            "notes": "Public-domain space/earth footage. Verify partner clips.",
        },
    }


async def search_stock(input: StockSearchInput) -> list[StockCandidate]:
    sources = input.get("sources") or DEFAULT_BAKE_SOURCES
    video_first = input.get("videoFirst", True)
    tasks = []
    if "pexels" in sources:
        tasks.append(search_pexels(input))
    if "pixabay" in sources:
        tasks.append(search_pixabay(input))
    if "coverr" in sources:
        tasks.append(search_coverr(input))
    if "nasa" in sources:
        tasks.append(search_nasa(input))
    if "unsplash" in sources:
        tasks.append(search_unsplash(input))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged: list[StockCandidate] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        merged.extend(result)
    videos = [c for c in merged if c["kind"] == "video" and not c["previewOnly"]]
    images = [c for c in merged if c["kind"] == "image" and not c["previewOnly"]]
    preview = [c for c in merged if c["previewOnly"]]
    ranked_videos = [c for c in videos if c["source"] != "pexels"] + [c for c in videos if c["source"] == "pexels"]
    if not video_first:
        return [*images, *ranked_videos, *preview]
    return [*ranked_videos, *images, *preview]


def pick_bakeable_candidate(candidates: list[StockCandidate]) -> StockCandidate | None:
    return next((c for c in candidates if not c["previewOnly"] and c["kind"] == "video"), None) or next(
        (c for c in candidates if not c["previewOnly"] and c["kind"] == "image"), None
    )


async def download_stock_candidate(candidate: StockCandidate, dest_dir: str | Path) -> DownloadedStock:
    if candidate["previewOnly"]:
        raise RuntimeError(f"{candidate['source']} assets are preview-only and cannot be downloaded into a render")
    ext = stock_file_extension(candidate)
    path = Path(dest_dir) / f"{candidate['id']}.{ext}"
    await download_url_to_file(candidate["downloadUrl"], path, source=candidate["source"])
    return {"candidate": candidate, "path": str(path)}
