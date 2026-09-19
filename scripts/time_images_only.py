from __future__ import annotations

import asyncio
import logging
import time

from app.db.connection import close_db, get_db
from app.db.models import create_reel, create_session, upsert_device
from app.services.stock_reel import generate_stock_media_reel
from app.storage.paths import ensure_storage_root


def _patch_timer(module: str, name: str, bucket: str, times: dict[str, float]) -> None:
    import importlib

    mod = importlib.import_module(module)
    original = getattr(mod, name)

    async def wrapped(*args, **kwargs):
        started = time.perf_counter()
        try:
            return await original(*args, **kwargs)
        finally:
            times[bucket] = times.get(bucket, 0.0) + (time.perf_counter() - started)

    setattr(mod, name, wrapped)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    times: dict[str, float] = {}
    _patch_timer("app.services.stock_reel", "render_kenburns_clip", "kenburns", times)
    _patch_timer("app.services.stock_reel", "produce_scene_clip", "scene_bake", times)
    _patch_timer("app.services.narration", "synthesize_affirmation", "tts", times)
    _patch_timer("app.services.narration", "burn_affirmation_overlay", "overlay", times)
    _patch_timer("app.services.narration", "assemble_reel", "assemble", times)
    _patch_timer("app.services.narration", "mix_speech_and_music", "mix", times)

    await get_db()
    await ensure_storage_root()
    device = await upsert_device()
    session = await create_session(device["device_id"], {"voice": "aria", "reel_variants": ["images_only"]})
    reel = await create_reel(session["session_id"], "images_only")
    print(f"session={session['session_id']} reel={reel['reel_id']}")
    started = time.perf_counter()
    try:
        await generate_stock_media_reel(session["session_id"], reel["reel_id"], "images_only")
    finally:
        total = time.perf_counter() - started
        print("--- stage times (seconds) ---")
        for key in ("kenburns", "scene_bake", "tts", "overlay", "assemble", "mix"):
            print(f"{key:12} {times.get(key, 0.0):6.1f}")
        print(f"{'TOTAL':12} {total:6.1f}")
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
