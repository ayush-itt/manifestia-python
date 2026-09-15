from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.config import config
from app.db.connection import now_iso
from app.db.models import insert_scene, set_scene_status, update_reel
from app.lib.seedance.generate import generate_seedance_video
from app.services.music import pick_background_music
from app.services.narration import finish_reel_with_affirmations
from app.services.story import load_story_template, resolve_reference_paths
from app.storage.paths import ensure_reel_dirs, scene_video_path


async def generate_ai_video_reel(session_id: str, reel_id: str) -> None:
    if not config.byteplus_api_key:
        raise RuntimeError("BYTEPLUS_API_KEY not set")

    story = await load_story_template()
    await ensure_reel_dirs(session_id, reel_id)
    await update_reel(reel_id, {"status": "generating", "started_at": now_iso(), "progress": 5})

    scene_ids: list[str] = []
    video_paths: list[str] = [""] * len(story["scenes"])

    for scene in story["scenes"]:
        scene_id = str(uuid.uuid4())
        scene_ids.append(scene_id)
        refs = resolve_reference_paths(scene.get("referenceImages") or [])
        await insert_scene(
            {
                "scene_id": scene_id,
                "reel_id": reel_id,
                "scene_index": scene["sceneId"],
                "title": scene["title"],
                "prompt": scene["prompt"],
                "voiceover": scene["voiceover"],
                "reference_images": json.dumps(refs),
                "media_type": "ai_video",
                "media_path": None,
                "duration_sec": scene.get("duration") or config.scene_duration_sec,
                "status": "queued",
                "stock_query": None,
                "stock_source": None,
                "error_message": None,
            }
        )

    import asyncio

    async def generate_one(i: int) -> None:
        scene = story["scenes"][i]
        scene_id = scene_ids[i]
        refs = resolve_reference_paths(scene.get("referenceImages") or [])
        await set_scene_status(scene_id, "generating")
        output_path = scene_video_path(session_id, reel_id, scene_id)
        try:
            await generate_seedance_video(
                {
                    "visualPrompt": scene["prompt"],
                    "referenceImagePaths": [ref["absolutePath"] for ref in refs],
                    "durationSec": scene.get("duration") or config.scene_duration_sec,
                    "ratio": story.get("ratio") or config.video_ratio,
                    "resolution": "720p",
                    "generateAudio": True,
                    "outputPath": str(output_path),
                    "sceneId": scene_id,
                }
            )
            if not output_path.exists():
                raise RuntimeError(f"Seedance output missing: {output_path}")
            await set_scene_status(scene_id, "ready", {"media_path": str(output_path), "media_type": "ai_video"})
            video_paths[i] = str(output_path)
            await update_reel(reel_id, {"progress": 10 + round(((i + 1) / len(story["scenes"])) * 50)})
        except Exception as err:
            msg = str(err) if str(err) else "Seedance scene failed"
            await set_scene_status(scene_id, "failed", {"error_message": msg})
            raise

    results = await asyncio.gather(*[generate_one(i) for i in range(len(story["scenes"]))], return_exceptions=True)
    failures = [r for r in results if isinstance(r, Exception)]
    if failures:
        raise RuntimeError("; ".join(str(f) for f in failures))

    music = await pick_background_music()
    await update_reel(reel_id, {"music_track_id": music["id"], "progress": 70})
    finished = await finish_reel_with_affirmations(
        session_id=session_id,
        reel_id=reel_id,
        ratio=story.get("ratio") or config.video_ratio,  # type: ignore[arg-type]
        scenes=[
            {
                "videoPath": video_paths[i],
                "voiceover": scene["voiceover"],
                "durationSec": scene.get("duration") or config.scene_duration_sec,
            }
            for i, scene in enumerate(story["scenes"])
        ],
        music_path=music["absolutePath"],
    )
    await update_reel(
        reel_id,
        {
            "status": "completed",
            "output_path": finished["outputPath"],
            "duration_sec": finished["durationSec"],
            "completed_at": now_iso(),
            "progress": 100,
            "error_message": None,
        },
    )
