from __future__ import annotations

from pathlib import Path

from app.config import config
from app.lib.ffmpeg.assembly import probe_video_duration_sec, run_ffmpeg
from app.lib.ffmpeg.kenburns_remap import decode_image_rgb24, encode_rgb24_kenburns
from app.types import KenBurnsAnimation


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


async def _write_cover_still(src: str | Path, dest: str | Path, width: int, height: int) -> None:
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height}"
    await run_ffmpeg(["-y", "-i", str(src), "-vf", vf, "-frames:v", "1", "-update", "1", "-q:v", "2", str(dest)])


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
    still_path = Path(f"{dest}.still.jpg")
    sign = 1 if (scene_index or 0) % 2 == 0 else -1
    await _write_cover_still(image_path, still_path, width, height)
    try:
        src = await decode_image_rgb24(still_path, width, height)
        await encode_rgb24_kenburns(src, dest, width, height, used_fps, frames, sign)
    finally:
        still_path.unlink(missing_ok=True)
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
