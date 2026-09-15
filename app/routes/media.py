from __future__ import annotations

from fastapi import APIRouter, Query

from app.lib.music.catalog import get_music_catalog, list_music_moods
from app.lib.music.search import search_music
from app.lib.stock.search import search_stock, stock_source_status
from app.mappers import map_music_public
from app.schemas.api import StockSearchQuery

router = APIRouter(prefix="/api/media", tags=["Media"])


def _query_string_list(value: list[str] | str | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [v.strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [t.strip() for t in value.split(",") if t.strip()]
    return None


@router.get("/music/moods")
async def music_moods():
    return {"moods": await list_music_moods()}


@router.get("/music/search")
async def music_search(
    tags: list[str] | str | None = Query(default=None),
    mood: str | None = Query(default=None),
    minDurationSec: float | None = Query(default=None),
    maxDurationSec: float | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=50),
):
    tag_list = _query_string_list(tags)
    query = {
        "tags": tag_list,
        "mood": mood,
        "minDurationSec": minDurationSec,
        "maxDurationSec": maxDurationSec,
        "limit": limit,
    }
    tracks = await search_music(query) if mood or tag_list else await get_music_catalog()  # type: ignore[arg-type]
    return {"count": len(tracks), "tracks": [map_music_public(t) for t in tracks]}


@router.get("/stock/sources")
async def stock_sources():
    return {"sources": stock_source_status()}


@router.get("/stock/search")
async def stock_search(
    query: str = Query(..., min_length=1),
    kind: str | None = Query(default=None),
    sources: list[str] | str | None = Query(default=None),
    videoFirst: bool | None = Query(default=None),
    perPage: int | None = Query(default=None, ge=1, le=40),
    page: int | None = Query(default=None, ge=1),
    orientation: str | None = Query(default=None),
):
    source_list = _query_string_list(sources)
    parsed = StockSearchQuery(
        query=query,
        kind=kind,  # type: ignore[arg-type]
        sources=source_list,  # type: ignore[arg-type]
        videoFirst=videoFirst,
        perPage=perPage,
        page=page,
        orientation=orientation,  # type: ignore[arg-type]
    )
    payload = parsed.model_dump(exclude_none=True)
    candidates = await search_stock(payload)  # type: ignore[arg-type]
    return {"count": len(candidates), "candidates": candidates}
