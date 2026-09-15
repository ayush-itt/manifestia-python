from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.config import config
from app.lib.seedance.modelark_client import (
    DEFAULT_MODELARK_BASE_URL,
    ModelArkClient,
    extract_video_url,
)
from app.lib.seedance.seedance_duration import assert_seedance_duration
from app.lib.seedance.seedance_media_url import resolve_image_url_for_seedance, resolve_video_url_for_seedance


async def _download_video(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        res = await client.get(url)
        if res.status_code >= 400:
            raise RuntimeError(f"Failed to download video: {res.status_code}")
        output_path.write_bytes(res.content)


def _assert_file_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{label} not found at {path}")


async def generate_seedance_video(input: dict[str, Any]) -> dict[str, Any]:
    api_key = config.byteplus_api_key
    if not api_key:
        raise RuntimeError("BYTEPLUS_API_KEY not set")

    base_url = config.byteplus_api_url or DEFAULT_MODELARK_BASE_URL
    model_id = config.byteplus_video_model
    public_base_url = config.public_api_url
    seedance_duration = assert_seedance_duration(input["durationSec"])
    ratio = input.get("ratio") or "9:16"
    generate_audio = input.get("generateAudio", True)
    image_paths = [Path(p) for p in (input.get("referenceImagePaths") or [])]
    video_paths = [Path(p) for p in (input.get("referenceVideoPaths") or [])]
    output_path = Path(input["outputPath"])
    scene_id = input.get("sceneId") or "unknown"

    for path in image_paths:
        _assert_file_exists(path, "Reference image")
    for path in video_paths:
        _assert_file_exists(path, "Reference video")

    client = ModelArkClient(api_key, base_url)
    content: list[dict[str, Any]] = [{"type": "text", "text": input["visualPrompt"]}]
    for image_path in image_paths:
        url = await resolve_image_url_for_seedance(image_path, public_base_url)
        content.append({"type": "image_url", "role": "reference_image", "image_url": {"url": url}})
    for video_path in video_paths:
        url = await resolve_video_url_for_seedance(video_path, public_base_url)
        content.append({"type": "video_url", "role": "reference_video", "video_url": {"url": url}})

    print(
        f"[seedance] Creating task scene={scene_id} model={model_id} duration={seedance_duration}s "
        f"ratio={ratio} images={len(image_paths)} videos={len(video_paths)}"
    )

    try:
        task = await client.create_video_task(
            {
                "model": model_id,
                "content": content,
                "ratio": ratio,
                "duration": seedance_duration,
                "resolution": input.get("resolution") or "720p",
                "generate_audio": generate_audio,
            }
        )

        def on_update(t: dict[str, Any]) -> None:
            if t.get("status") in ("running", "queued"):
                print(f"[seedance] task {task.get('id')} status={t.get('status')}")

        final_task = await client.poll_task(task["id"], interval_ms=3500, on_update=on_update)
        if final_task.get("status") != "succeeded":
            err = (final_task.get("error") or {}).get("message") or f"Seedance task {final_task.get('status')}"
            raise RuntimeError(err)
        video_url = extract_video_url(final_task)
        if not video_url:
            raise RuntimeError("Seedance task succeeded but no video URL returned")
        await _download_video(video_url, output_path)
        print(f"[seedance] Video ready scene={scene_id} task={task.get('id')}")
        return {"videoPath": str(output_path), "provider": "seedance", "taskId": task["id"]}
    except Exception as err:
        msg = str(err)
        print(f"[seedance] failed scene={scene_id}:", msg)
        raise
