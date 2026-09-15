from __future__ import annotations

from typing import TypedDict

from app.lib.music.catalog import get_music_catalog
from app.types import MusicTrack


class MusicSearchQuery(TypedDict, total=False):
    tags: list[str]
    mood: str
    minDurationSec: float
    maxDurationSec: float
    limit: int


def _normalize(value: str) -> str:
    return value.strip().lower()


def _score_track(track: MusicTrack, query: MusicSearchQuery) -> float:
    score = 0.0
    mood = _normalize(query.get("mood") or "")
    if mood and _normalize(track["mood"]) == mood:
        score += 100

    wanted = [_normalize(t) for t in (query.get("tags") or []) if t]
    if wanted:
        haystack = {_normalize(track["mood"]), _normalize(track["title"]), *(_normalize(t) for t in track["tags"])}
        for tag in wanted:
            if tag in haystack:
                score += 10
            else:
                for token in haystack:
                    if tag in token or token in tag:
                        score += 4
                        break

    min_d = query.get("minDurationSec")
    max_d = query.get("maxDurationSec")
    if min_d is not None and track["durationSec"] >= min_d:
        score += 5
    if max_d is not None and track["durationSec"] <= max_d:
        score += 5
    if min_d is not None and max_d is not None:
        mid = (min_d + max_d) / 2
        delta = abs(track["durationSec"] - mid)
        if delta <= 30:
            score += 10
        elif delta <= 90:
            score += 3
    if min_d is not None and track["durationSec"] < min_d:
        score -= 8
    return score


async def search_music(query: MusicSearchQuery) -> list[MusicTrack]:
    tracks = await get_music_catalog()
    limit = max(1, min(query.get("limit") or 12, 50))
    scored: list[MusicTrack] = []
    for track in tracks:
        item = dict(track)
        item["score"] = _score_track(track, query)
        scored.append(item)  # type: ignore[arg-type]
    scored.sort(key=lambda t: (-(t.get("score") or 0), t["title"]))
    has_query = bool(query.get("mood")) or bool(query.get("tags"))
    if not has_query:
        return scored[:limit]
    return [t for t in scored if (t.get("score") or 0) > 0][:limit]
