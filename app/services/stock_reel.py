from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from app.config import config
from app.db.connection import now_iso
from app.db.models import insert_scene, set_scene_status, update_reel
from app.lib.ffmpeg.assembly import ffmpeg_path, run_ffmpeg
from app.lib.ffmpeg.kenburns import add_silent_audio, normalize_stock_video_clip, render_kenburns_clip
from app.services.music import pick_background_music
from app.services.narration import finish_reel_with_affirmations
from app.services.story import load_story_template, resolve_local_video_path, resolve_reference_paths, stock_query_for_scene
from app.storage.paths import ensure_reel_dirs, scene_video_path
from app.types import StockReelMode, StoryScene

logger = logging.getLogger(__name__)

PERSONALIZED_STILL_ROLE = "personalized_still"
STYLE_REFERENCE_ROLE = "style_reference"
STILLS_PER_SCENE = 2
STILL_SEGMENT_SEC = 5.0
FORBIDDEN_PERSONALIZED_FILES = frozenset({"subject_reference.jpg"})


def _file_basename(rel: str) -> str:
    return Path(rel).name.lower()


def style_reference_images(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in refs if (r.get("role") or "") == STYLE_REFERENCE_ROLE]


def resolve_personalized_still(scene: StoryScene) -> dict[str, Any]:
    rel = (scene.get("personalizedStill") or "").strip()
    if not rel:
        raise RuntimeError(
            f"Scene {scene['sceneId']} ({scene['title']}) is missing personalizedStill. "
            "Do not substitute subject_identity, customer_identity, or family_member_identity."
        )
    if _file_basename(rel) in FORBIDDEN_PERSONALIZED_FILES:
        raise RuntimeError(
            f"Scene {scene['sceneId']} cannot use {rel} as a personalized still. "
            "subject_reference.jpg is an identity sheet, not a photoreal founder still."
        )
    path = (config.story_assets_dir / rel).resolve()
    if not path.is_file():
        raise RuntimeError(f"Scene {scene['sceneId']} personalized still missing on disk: {rel}")
    return {"file": rel, "role": PERSONALIZED_STILL_ROLE, "absolutePath": str(path)}


def resolve_generic_style_still(scene: StoryScene) -> dict[str, Any]:
    refs = resolve_reference_paths(scene.get("referenceImages") or [])
    styles = style_reference_images(refs)
    if not styles:
        raise RuntimeError(
            f"Scene {scene['sceneId']} ({scene['title']}) has no style_reference still. "
            "customer_identity, family_member_identity, and subject_identity cannot be used as generic."
        )
    chosen = styles[0]
    path = chosen.get("absolutePath")
    if not path or not Path(str(path)).is_file():
        raise RuntimeError(
            f"Scene {scene['sceneId']} generic style still missing on disk: {chosen.get('file') or path}"
        )
    return chosen


def personalized_and_generic_stills(scene: StoryScene) -> list[dict[str, Any]]:
    return [resolve_personalized_still(scene), resolve_generic_style_still(scene)]


def validate_local_reel_assets(scenes: list[StoryScene], mode: StockReelMode) -> None:
    for scene in scenes:
        if mode == "mixed" and (scene.get("localVideo") or "").strip():
            resolve_local_video_path(scene)
            continue
        personalized_and_generic_stills(scene)


async def generate_stock_media_reel(session_id: str, reel_id: str, mode: StockReelMode = "mixed") -> None:
    story = await load_story_template()
    await ensure_reel_dirs(session_id, reel_id)
    await update_reel(reel_id, {"status": "generating", "started_at": now_iso(), "progress": 5})
    logger.info("stock reel start reel=%s session=%s mode=%s scenes=%s", reel_id, session_id, mode, len(story["scenes"]))
    validate_local_reel_assets(story["scenes"], mode)

    scene_ids: list[str] = []
    video_paths: list[str] = [""] * len(story["scenes"])

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
        duration_sec = scene.get("duration") or config.scene_duration_sec
        await set_scene_status(scene_id, "generating")
        logger.info("stock scene start reel=%s scene=%s index=%s mode=%s", reel_id, scene_id, scene["sceneId"], mode)
        try:
            processed = await produce_scene_clip(
                session_id=session_id,
                reel_id=reel_id,
                scene_id=scene_id,
                scene=scene,
                mode=mode,
                duration_sec=duration_sec,
            )
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
            logger.info(
                "stock scene ready reel=%s scene=%s type=%s source=%s",
                reel_id,
                scene_id,
                processed["mediaType"],
                processed["source"],
            )
            await update_reel(reel_id, {"progress": 10 + round(((i + 1) / len(story["scenes"])) * 50)})
        except Exception as err:
            msg = str(err).strip() or type(err).__name__
            logger.error("stock scene failed reel=%s scene=%s: %s", reel_id, scene_id, msg)
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
    logger.info("stock reel complete reel=%s mode=%s output=%s", reel_id, mode, finished["outputPath"])


async def produce_scene_clip(
    session_id: str,
    reel_id: str,
    scene_id: str,
    scene: StoryScene,
    mode: StockReelMode,
    duration_sec: float,
) -> dict[str, str]:
    out_path = scene_video_path(session_id, reel_id, scene_id)
    silent_path = f"{out_path}.silent.mp4"
    if mode == "mixed" and (scene.get("localVideo") or "").strip():
        return await bake_local_video(scene, silent_path, str(out_path), duration_sec)
    return await bake_two_local_stills(scene, silent_path, str(out_path), duration_sec)


async def bake_local_video(scene: StoryScene, silent_path: str, out_path: str, duration_sec: float) -> dict[str, str]:
    source = resolve_local_video_path(scene)
    await normalize_stock_video_clip(
        input_path=source,
        output_path=silent_path,
        width=config.video_width,
        height=config.video_height,
        duration_sec=duration_sec,
        fps=config.video_fps,
    )
    await add_silent_audio(silent_path, out_path, duration_sec)
    rel = (scene.get("localVideo") or "").strip()
    return {"path": out_path, "mediaType": "ai_video", "source": f"local:{rel}"}


async def bake_two_local_stills(
    scene: StoryScene,
    silent_path: str,
    out_path: str,
    duration_sec: float,
) -> dict[str, str]:
    images = personalized_and_generic_stills(scene)
    segment = duration_sec / STILLS_PER_SCENE if duration_sec else STILL_SEGMENT_SEC
    dest = Path(silent_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    segments: list[str] = []
    for i, image in enumerate(images):
        image_path = image.get("absolutePath")
        if not image_path or not Path(image_path).is_file():
            raise RuntimeError(
                f"Scene {scene['sceneId']} still missing on disk: {image.get('file') or image_path}"
            )
        segment_path = f"{silent_path}.still-{i}.mp4"
        await render_kenburns_clip(
            image_path=image_path,
            output_path=segment_path,
            width=config.video_width,
            height=config.video_height,
            duration_sec=segment,
            fps=config.video_fps,
            animation="ken-burns",
            scene_index=scene["sceneId"] + i,
        )
        segments.append(segment_path)
    await concat_silent_clips(segments, silent_path)
    await add_silent_audio(silent_path, out_path, duration_sec)
    joined = "+".join(str(image.get("file") or image.get("absolutePath")) for image in images)
    return {"path": out_path, "mediaType": "stock_image", "source": f"local:{joined}"}


async def concat_silent_clips(clips: list[str], output_path: str) -> None:
    if not clips:
        raise RuntimeError("No still clips to concatenate")
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_path = Path(f"{output_path}.list.txt")
    list_content = "\n".join(
        f"file '{ffmpeg_path(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'" for p in clips
    )
    list_path.write_text(list_content, encoding="utf-8")
    await run_ffmpeg(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest),
        ]
    )
