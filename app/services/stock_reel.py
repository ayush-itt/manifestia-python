from __future__ import annotations

import json
import uuid
from typing import Any

from app.config import config
from app.db.connection import now_iso
from app.db.models import insert_scene, set_scene_status, update_reel
from app.lib.ffmpeg.kenburns import add_silent_audio, normalize_stock_video_clip, render_kenburns_clip
from app.lib.stock.search import download_stock_candidate, search_stock
from app.services.music import pick_background_music
from app.services.narration import finish_reel_with_affirmations
from app.services.story import load_story_template, resolve_reference_paths, stock_query_for_scene
from app.storage.paths import ensure_reel_dirs, scene_video_path, stock_dest_dir
from app.types import StockCandidate, StockReelMode, StoryScene

MOTION_WORDS = [
    "water", "ocean", "city", "walk", "walking", "sky", "wave", "waves",
    "cloud", "clouds", "rain", "river", "traffic", "crowd", "dance",
    "sunrise", "sunset", "wind", "sea", "beach", "street", "night",
    "aerial", "drone", "flow", "moving", "light", "coast", "forest",
    "skyline", "rooftop",
]


def pick_fallback_image(refs: list[dict[str, Any]]) -> str | None:
    preferred = next((r for r in reversed(refs) if r.get("role") != "subject_identity"), None)
    if preferred:
        return preferred.get("absolutePath")
    if refs:
        return refs[-1].get("absolutePath") or refs[0].get("absolutePath")
    return None


def motion_score(text: str) -> int:
    lowered = text.lower()
    return sum(1 for word in MOTION_WORDS if word in lowered)


def video_slot_indices(scenes: list[StoryScene]) -> set[int]:
    n = len(scenes)
    if n < 2:
        return set()
    target = min(max(round(n * 0.33), 1), n // 2)
    picked: list[int] = []
    for k in range(target):
        pos = int(((k + 0.5) * n) / target)
        remaining = [i for i in range(n) if i not in picked]

        def sort_key(idx: int) -> tuple[int, int, int]:
            consec = 1 if any(abs(idx - p) == 1 for p in picked) else 0
            dist = abs(idx - pos)
            score = motion_score(f"{scenes[idx]['voiceover']} {scenes[idx]['title']}")
            return (consec, dist, -score)

        remaining.sort(key=sort_key)
        picked.append(remaining[0])
    return set(picked)


async def generate_stock_media_reel(session_id: str, reel_id: str, mode: StockReelMode = "mixed") -> None:
    story = await load_story_template()
    await ensure_reel_dirs(session_id, reel_id)
    await update_reel(reel_id, {"status": "generating", "started_at": now_iso(), "progress": 5})

    scene_ids: list[str] = []
    video_paths: list[str] = [""] * len(story["scenes"])
    video_slots = video_slot_indices(story["scenes"]) if mode == "mixed" else set()
    used_keys: set[str] = set()

    for scene in story["scenes"]:
        scene_id = str(uuid.uuid4())
        scene_ids.append(scene_id)
        query = stock_query_for_scene(story, scene["sceneId"], scene["title"])
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
                "media_type": None,
                "media_path": None,
                "duration_sec": scene.get("duration") or config.scene_duration_sec,
                "status": "queued",
                "stock_query": query,
                "stock_source": None,
                "error_message": None,
            }
        )

    for i, scene in enumerate(story["scenes"]):
        scene_id = scene_ids[i]
        query = stock_query_for_scene(story, scene["sceneId"], scene["title"])
        await set_scene_status(scene_id, "generating")
        try:
            processed = await produce_scene_clip(
                session_id=session_id,
                reel_id=reel_id,
                scene_id=scene_id,
                scene_index=scene["sceneId"],
                query=query,
                want_video=i in video_slots,
                used_keys=used_keys,
                fallback_image=pick_fallback_image(resolve_reference_paths(scene.get("referenceImages") or [])),
                duration_sec=scene.get("duration") or config.scene_duration_sec,
            )
            used_keys.add(processed["source"])
            await set_scene_status(
                scene_id,
                "ready",
                {
                    "media_path": processed["path"],
                    "media_type": processed["mediaType"],
                    "stock_source": processed["source"],
                },
            )
            video_paths[i] = processed["path"]
            await update_reel(reel_id, {"progress": 10 + round(((i + 1) / len(story["scenes"])) * 50)})
        except Exception as err:
            msg = str(err) if str(err) else "Stock scene failed"
            await set_scene_status(scene_id, "failed", {"error_message": msg})
            raise

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


async def produce_scene_clip(
    session_id: str,
    reel_id: str,
    scene_id: str,
    scene_index: int,
    query: str,
    want_video: bool,
    used_keys: set[str],
    fallback_image: str | None,
    duration_sec: float,
) -> dict[str, str]:
    dest_dir = stock_dest_dir(session_id, reel_id, scene_id)
    out_path = scene_video_path(session_id, reel_id, scene_id)
    silent_path = f"{out_path}.silent.mp4"

    if want_video:
        clip = await try_stock_video(query, dest_dir, silent_path, str(out_path), duration_sec, used_keys)
        if clip:
            return clip
        print(f"[stock scene {scene_id}] video slot fell back to still")

    try:
        candidates = await search_stock(
            {
                "query": query,
                "kind": "image",
                "perPage": 8,
                "orientation": "portrait",
                "sources": ["pexels", "pixabay", "unsplash"],
            }
        )
        images = [
            c
            for c in candidates
            if not c["previewOnly"] and c["kind"] == "image" and f"{c['source']}:{c['sourceId']}" not in used_keys
        ]
        for picked in images:
            try:
                return await bake_still(picked, dest_dir, silent_path, str(out_path), duration_sec, scene_index)
            except Exception as err:
                print(f"[stock scene {scene_id}] image {picked['id']} failed:", err)
    except Exception as err:
        print(f"[stock scene {scene_id}] image search failed:", err)

    if not fallback_image:
        raise RuntimeError(f"No stock media found for query: {query}")
    await render_kenburns_clip(
        image_path=fallback_image,
        output_path=silent_path,
        width=config.video_width,
        height=config.video_height,
        duration_sec=duration_sec,
        fps=config.video_fps,
        animation="ken-burns",
        scene_index=scene_index,
    )
    await add_silent_audio(silent_path, out_path, duration_sec)
    return {"path": str(out_path), "mediaType": "stock_image", "source": f"fallback:{fallback_image}"}


async def try_stock_video(
    query: str,
    dest_dir,
    silent_path: str,
    out_path: str,
    duration_sec: float,
    used_keys: set[str],
) -> dict[str, str] | None:
    try:
        candidates = await search_stock(
            {
                "query": query,
                "kind": "video",
                "videoFirst": True,
                "perPage": 8,
                "orientation": "portrait",
                "sources": ["pixabay", "coverr", "pexels"],
            }
        )
        ordered = [
            c
            for c in rank_video_candidates(candidates)
            if not c["previewOnly"] and f"{c['source']}:{c['sourceId']}" not in used_keys
        ]
        for picked in ordered:
            try:
                downloaded = await download_stock_candidate(picked, dest_dir)
                await normalize_stock_video_clip(
                    input_path=downloaded["path"],
                    output_path=silent_path,
                    width=config.video_width,
                    height=config.video_height,
                    duration_sec=duration_sec,
                    fps=config.video_fps,
                )
                await add_silent_audio(silent_path, out_path, duration_sec)
                return {
                    "path": out_path,
                    "mediaType": "stock_video",
                    "source": f"{picked['source']}:{picked['sourceId']}",
                }
            except Exception as err:
                print(f"[stock video] {picked['id']} failed:", err)
    except Exception as err:
        print("[stock video] search failed:", err)
    return None


def rank_video_candidates(candidates: list[StockCandidate]) -> list[StockCandidate]:
    videos = [c for c in candidates if c["kind"] == "video"]
    return [c for c in videos if c["source"] != "pexels"] + [c for c in videos if c["source"] == "pexels"]


async def bake_still(
    picked: StockCandidate,
    dest_dir,
    silent_path: str,
    out_path: str,
    duration_sec: float,
    scene_index: int,
) -> dict[str, str]:
    downloaded = await download_stock_candidate(picked, dest_dir)
    await render_kenburns_clip(
        image_path=downloaded["path"],
        output_path=silent_path,
        width=config.video_width,
        height=config.video_height,
        duration_sec=duration_sec,
        fps=config.video_fps,
        animation="ken-burns",
        scene_index=scene_index,
    )
    await add_silent_audio(silent_path, out_path, duration_sec)
    return {
        "path": out_path,
        "mediaType": "stock_image",
        "source": f"{picked['source']}:{picked['sourceId']}",
    }
