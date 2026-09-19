from __future__ import annotations

import json
from pathlib import Path

from app.config import config
from app.db.models import get_session, update_reel
from app.lib.ffmpeg.assembly import assemble_reel, probe_video_duration_sec
from app.lib.ffmpeg.narration import concat_audio_files, mix_speech_and_music, mux_video_with_audio, pad_scene_narration
from app.lib.ffmpeg.overlay import burn_affirmation_overlay
from app.lib.timing import caption_fade_times, centered_voice_delay
from app.lib.tts.synthesize import synthesize_affirmation
from app.storage.paths import final_render_path, reel_dir
from app.types import ReelRatio


async def voice_id_from_session(session_id: str) -> str:
    session = await get_session(session_id)
    if not session:
        return "aria"
    try:
        answers = json.loads(session.get("onboarding_answers") or "{}")
        voice = answers.get("voice")
        if isinstance(voice, str) and voice.strip():
            return voice.strip()
        return "aria"
    except json.JSONDecodeError:
        return "aria"


async def finish_reel_with_affirmations(
    session_id: str,
    reel_id: str,
    ratio: ReelRatio,
    scenes: list[dict],
    music_path: str,
) -> dict[str, float | str]:
    voice_id = await voice_id_from_session(session_id)
    work_dir = reel_dir(session_id, reel_id) / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    overlaid: list[str] = []
    padded: list[str] = []

    for i, scene in enumerate(scenes):
        await update_reel(
            reel_id,
            {"progress": 70 + round(((i + 0.5) / max(len(scenes), 1)) * 20)},
        )
        tts_path = work_dir / f"tts-{i}.mp3"
        await synthesize_affirmation(scene["voiceover"], voice_id, tts_path)
        duration_sec = float(scene["durationSec"])
        try:
            audio_len = await probe_video_duration_sec(tts_path)
            delay = centered_voice_delay(duration_sec, audio_len)
        except Exception:
            delay = config.narration_delay_sec
            audio_len = max(duration_sec - 2 * delay, 0.1)
        timings = caption_fade_times(duration_sec, delay, audio_len)
        overlay_path = work_dir / f"overlay-{i}.mp4"
        await burn_affirmation_overlay(
            scene["videoPath"],
            overlay_path,
            scene["voiceover"],
            duration_sec,
            caption_start=timings["caption_start"],
            fade_in_sec=timings["fade_in_sec"],
            fade_out_start=timings["fade_out_start"],
            fade_out_sec=timings["fade_out_sec"],
        )
        overlaid.append(str(overlay_path))
        padded_path = work_dir / f"tts-{i}-pad.m4a"
        await pad_scene_narration(tts_path, padded_path, duration_sec, delay)
        padded.append(str(padded_path))

    concat_path = Path(f"{final_render_path(session_id, reel_id)}.concat.mp4")
    assembled = await assemble_reel(ratio, overlaid, concat_path)
    narration_path = work_dir / "narration.m4a"
    await concat_audio_files(padded, narration_path)
    mix_path = work_dir / "mix.m4a"
    await mix_speech_and_music(narration_path, music_path, mix_path)
    output_path = final_render_path(session_id, reel_id)
    await mux_video_with_audio(assembled["outputPath"], mix_path, output_path)
    try:
        duration_sec = await probe_video_duration_sec(output_path)
    except Exception:
        duration_sec = float(assembled["totalDurationSec"])
    return {"outputPath": str(output_path), "durationSec": duration_sec}
