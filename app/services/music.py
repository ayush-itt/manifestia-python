from __future__ import annotations

from app.lib.music.search import search_music
from app.services.story import load_story_template
from app.types import MusicTrack


async def pick_background_music() -> MusicTrack:
    story = await load_story_template()
    matches = await search_music(
        {
            "tags": story["tags"],
            "mood": story["mood"],
            "minDurationSec": 55,
            "maxDurationSec": 180,
            "limit": 5,
        }
    )
    if matches:
        return matches[0]
    fallback = await search_music({"mood": story["mood"], "limit": 1})
    if fallback:
        return fallback[0]
    any_track = await search_music({"limit": 1})
    if not any_track:
        raise RuntimeError("No background music tracks found in content/background-music")
    return any_track[0]
