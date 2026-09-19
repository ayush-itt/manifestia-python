from __future__ import annotations

import json
import re
from typing import Any

from pathlib import Path

from app.config import config
from app.types import ReelRatio, StoryReferenceImage, StoryScene, StoryTemplate


def extract_voiceover(scene: dict[str, Any]) -> str:
    voiceover = scene.get("voiceover")
    if isinstance(voiceover, str) and voiceover.strip():
        return voiceover.strip()
    prompt = scene.get("prompt") if isinstance(scene.get("prompt"), str) else ""
    match = re.search(r'Voiceover:\s*(?:\*[^*]*\*\s*)?[“"]([^”"]+)[”"]', prompt, re.I)
    if not match:
        match = re.search(r'Voiceover:[^\n]*"([^"]+)"', prompt, re.I)
    if match and match.group(1):
        return match.group(1).strip()
    return str(scene.get("title") or "")


async def load_story_template() -> StoryTemplate:
    raw = json.loads(config.story_path.read_text(encoding="utf-8"))
    ratio: ReelRatio = raw.get("ratio") or raw.get("aspectRatio") or config.video_ratio
    if ratio not in ("9:16", "16:9"):
        ratio = config.video_ratio  # type: ignore[assignment]
    scenes: list[StoryScene] = []
    for scene in raw.get("scenes") or []:
        scenes.append(
            {
                "sceneId": int(scene["sceneId"]),
                "title": scene.get("title") or "",
                "timecode": scene.get("timecode") or scene.get("time-code") or "",
                "duration": float(scene.get("duration") if scene.get("duration") is not None else config.scene_duration_sec),
                "prompt": scene.get("prompt") or "",
                "stockQuery": (scene.get("stockQuery") or "").strip(),
                "voiceover": extract_voiceover(scene),
                "referenceImages": scene.get("referenceImages") or [],
                "localVideo": (scene.get("localVideo") or "").strip(),
                "personalizedStill": (scene.get("personalizedStill") or "").strip(),
                "generalizedStill": (scene.get("generalizedStill") or "").strip(),
            }
        )
    return {
        "id": raw.get("id") or "",
        "title": raw.get("title") or "",
        "ratio": ratio,
        "mood": raw.get("mood") or "hopeful",
        "tags": raw.get("tags") or [],
        "script": raw.get("script") or "",
        "scenes": scenes,
    }


def resolve_reference_paths(images: list[StoryReferenceImage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for img in images:
        item = dict(img)
        item["absolutePath"] = str(config.story_assets_dir / img["file"])
        out.append(item)
    return out


def resolve_local_video_path(scene: StoryScene) -> Path:
    rel = (scene.get("localVideo") or "").strip()
    if not rel:
        raise RuntimeError(f"Scene {scene['sceneId']} has no localVideo path")
    path = (config.story_assets_dir / rel).resolve()
    if not path.is_file():
        raise RuntimeError(f"Local AI video not found for scene {scene['sceneId']}: {rel}")
    return path


def stock_query_for_scene(story: StoryTemplate, scene_id: int, fallback_title: str) -> str:
    found = next((s for s in story["scenes"] if s["sceneId"] == scene_id), None)
    if found and found.get("stockQuery"):
        return found["stockQuery"]
    cleaned = re.sub(r"[^a-z0-9\s]", " ", fallback_title.lower())
    return re.sub(r"\s+", " ", cleaned).strip()
