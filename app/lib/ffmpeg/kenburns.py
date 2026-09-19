from __future__ import annotations

from pathlib import Path

from app.config import config
from app.lib.ffmpeg.assembly import probe_video_duration_sec, run_ffmpeg
from app.types import KenBurnsAnimation

KENBURNS_ZOOM = 0.20
KENBURNS_TX = 0.03
KENBURNS_TY = 0.015


def _clip_start_offset(clip_duration: float, hold: float) -> float:
    if clip_duration <= hold + 0.05:
        return 0
    leftover = clip_duration - hold
    offset = 0.8 if leftover >= 0.8 else 0
    if clip_duration >= hold * 2:
        offset = min(max(clip_duration * 0.1, 0.8), 3)
    if offset + hold > clip_duration:
        offset = max(clip_duration - hold, 0)
    return offset


def _even(value: int) -> int:
    return value + (value % 2)


def kenburns_filter(width: int, height: int, frames: int, sign: int, fps: int | None = None) -> str:
    over_w = _even(round(width * (1 + KENBURNS_ZOOM)))
    over_h = _even(round(height * (1 + KENBURNS_ZOOM)))
    last = max(frames - 1, 1)
    used_fps = fps or config.video_fps
    ease = f"(0.5-0.5*cos(PI*n/{last}))"
    zoom = f"(1+{KENBURNS_ZOOM}*{ease})"
    pan = 1 if sign >= 0 else -1
    x = f"max(0\\,min(iw-ow\\,(iw-ow)/2+({pan})*iw*{KENBURNS_TX}*{ease}))"
    y = f"max(0\\,min(ih-oh\\,(ih-oh)/2+({pan})*ih*{KENBURNS_TY}*{ease}))"
    loops = max(frames - 1, 0)
    return (
        f"scale={over_w}:{over_h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={over_w}:{over_h},"
        f"loop={loops}:1:0,"
        f"setpts=N/{used_fps}/TB,"
        f"crop=w=iw/{zoom}:h=ih/{zoom}:x={x}:y={y},"
        f"scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p"
    )


def _h264_args(fps: int) -> list[str]:
    return [
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-fps_mode",
        "cfr",
        "-movflags",
        "+faststart",
    ]


async def render_kenburns_ffmpeg(
    image_path: str | Path,
    output_path: str | Path,
    width: int,
    height: int,
    animation: KenBurnsAnimation,
    duration_sec: float | None = None,
    fps: int | None = None,
    scene_index: int | None = None,
) -> str:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    used_fps = fps or config.video_fps
    duration = max(duration_sec if duration_sec is not None else config.scene_duration_sec, 0.1)
    frames = max(round(duration * used_fps), used_fps)
    sign = 1 if (scene_index or 0) % 2 == 0 else -1
    vf = kenburns_filter(width, height, frames, sign, used_fps)
    await run_ffmpeg(
        [
            "-y",
            "-framerate",
            str(used_fps),
            "-i",
            str(image_path),
            "-vf",
            vf,
            "-frames:v",
            str(frames),
            "-t",
            f"{duration:.3f}",
            *_h264_args(used_fps),
            str(dest),
        ]
    )
    return str(dest)


async def render_kenburns_clip(
    image_path: str | Path,
    output_path: str | Path,
    width: int,
    height: int,
    animation: KenBurnsAnimation,
    duration_sec: float | None = None,
    fps: int | None = None,
    scene_index: int | None = None,
) -> dict[str, str]:
    await render_kenburns_ffmpeg(image_path, output_path, width, height, animation, duration_sec, fps, scene_index)
    return {"path": str(output_path), "renderer": "ffmpeg"}


async def normalize_stock_video_clip(
    input_path: str | Path,
    output_path: str | Path,
    width: int,
    height: int,
    duration_sec: float | None = None,
    fps: int | None = None,
) -> str:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    used_fps = fps or config.video_fps
    duration = duration_sec if duration_sec is not None else config.scene_duration_sec
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},setsar=1,fps={used_fps},format=yuv420p"
    )
    try:
        native = await probe_video_duration_sec(input_path)
    except Exception:
        native = 0
    need_loop = native <= 0 or native < duration - 0.05
    offset = 0 if need_loop else _clip_start_offset(native, duration)
    args = ["-y"]
    if need_loop:
        args.extend(["-stream_loop", "-1"])
    if offset > 0:
        args.extend(["-ss", f"{offset:.3f}"])
    args.extend(["-i", str(input_path), "-t", str(duration), "-vf", vf, *_h264_args(used_fps), str(dest)])
    await run_ffmpeg(args)
    return str(dest)


async def add_silent_audio(input_path: str | Path, output_path: str | Path, duration_sec: float) -> str:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(input_path),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-t",
            str(duration_sec),
            str(dest),
        ]
    )
    return str(dest)
