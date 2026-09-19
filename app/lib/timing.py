from __future__ import annotations

from typing import TypedDict

CAPTION_FADE_IN_SEC = 0.35
CAPTION_FADE_OUT_SEC = 0.45
CAPTION_LEAD_SEC = 0.20
CAPTION_HOLD_AFTER_VOICE_SEC = 0.15


class CaptionFadeTimes(TypedDict):
    caption_start: float
    fade_in_sec: float
    fade_out_start: float
    fade_out_sec: float
    voice_delay_sec: float
    voice_end_sec: float


def centered_voice_delay(scene_duration_sec: float, audio_length_sec: float) -> float:
    duration = max(float(scene_duration_sec), 0.1)
    audio = min(max(float(audio_length_sec), 0.0), duration)
    return max((duration - audio) / 2.0, 0.0)


def caption_fade_times(
    scene_duration_sec: float,
    voice_delay_sec: float,
    audio_length_sec: float,
    *,
    fade_in_sec: float = CAPTION_FADE_IN_SEC,
    fade_out_sec: float = CAPTION_FADE_OUT_SEC,
    lead_sec: float = CAPTION_LEAD_SEC,
    hold_after_voice_sec: float = CAPTION_HOLD_AFTER_VOICE_SEC,
) -> CaptionFadeTimes:
    duration = max(float(scene_duration_sec), 0.1)
    delay = max(float(voice_delay_sec), 0.0)
    audio = min(max(float(audio_length_sec), 0.0), duration)

    if delay <= 0:
        fade_in = min(fade_in_sec, 0.12)
        caption_start = 0.0
    elif delay < fade_in_sec + lead_sec:
        fade_in = min(fade_in_sec, max(0.05, delay - 0.05))
        caption_start = 0.0
        if caption_start + fade_in > delay:
            fade_in = max(0.05, delay)
    else:
        fade_in = fade_in_sec
        caption_start = max(0.0, delay - fade_in - lead_sec)

    voice_end = min(delay + audio, duration)
    fade_out = min(fade_out_sec, max(0.1, duration - 0.05))
    earliest_out = caption_start + fade_in + 0.5
    fade_out_start = min(duration - fade_out, max(voice_end + hold_after_voice_sec, earliest_out))
    if fade_out_start <= caption_start + fade_in:
        fade_out_start = min(duration - fade_out, caption_start + fade_in + 0.2)
    if fade_out_start < caption_start:
        fade_out_start = max(caption_start, duration - fade_out)

    return {
        "caption_start": caption_start,
        "fade_in_sec": fade_in,
        "fade_out_start": fade_out_start,
        "fade_out_sec": fade_out,
        "voice_delay_sec": delay,
        "voice_end_sec": voice_end,
    }
