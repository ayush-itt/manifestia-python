from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Callable

from app.config import config
from app.types import ReelRatio


def _popen_kwargs() -> dict[str, int]:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _run_exec(
    cmd: str,
    args: list[str],
    *,
    stdin_bytes: bytes | None = None,
    stdin_devnull: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    kwargs: dict = {
        "args": [cmd, *args],
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "check": False,
        **_popen_kwargs(),
    }
    if stdin_bytes is not None:
        kwargs["input"] = stdin_bytes
    elif stdin_devnull:
        kwargs["stdin"] = subprocess.DEVNULL
    return subprocess.run(**kwargs)


def dimensions_for_ratio(ratio: ReelRatio) -> dict[str, int]:
    if ratio == "16:9":
        return {"width": config.video_height, "height": config.video_width}
    return {"width": config.video_width, "height": config.video_height}


async def run_command(cmd: str, args: list[str]) -> tuple[str, str]:
    # Threaded subprocess: Windows uvicorn uses SelectorEventLoop, which cannot spawn children.
    proc = await asyncio.to_thread(_run_exec, cmd, args)
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd} exited {proc.returncode}: {stderr[-800:]}")
    return stdout, stderr


async def run_ffmpeg(args: list[str]) -> None:
    proc = await asyncio.to_thread(_run_exec, "ffmpeg", args)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg exited {proc.returncode}: {stderr[-800:]}")


async def probe_video_duration_sec(video_path: str | Path) -> float:
    stdout, _ = await run_command(
        "ffprobe",
        [
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
    )
    try:
        value = float(stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Could not probe duration for {video_path}") from exc
    if value <= 0:
        raise RuntimeError(f"Could not probe duration for {video_path}")
    return value


async def has_audio_stream(video_path: str | Path) -> bool:
    try:
        stdout, _ = await run_command(
            "ffprobe",
            [
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(video_path),
            ],
        )
        return bool(stdout.strip())
    except Exception:
        return False


def ffmpeg_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


async def normalize_scene_video(input_path: str | Path, output_path: str | Path, ratio: ReelRatio) -> None:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dims = dimensions_for_ratio(ratio)
    width, height = dims["width"], dims["height"]
    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={config.video_fps}"
    )
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(input_path),
            "-vf",
            scale_filter,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            str(dest),
        ]
    )


async def assemble_reel(
    ratio: ReelRatio,
    scene_video_paths: list[str],
    output_path: str | Path,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, float | str]:
    videos = [p for p in scene_video_paths if p]
    if not videos:
        raise RuntimeError("No scene videos available for assembly")
    for path in videos:
        if not Path(path).exists():
            raise FileNotFoundError(path)
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if on_progress:
        on_progress(10)
    normalized_paths: list[str] = []
    durations: list[float] = []
    for i, video in enumerate(videos):
        normalized = f"{dest}.norm-{i}.mp4"
        await normalize_scene_video(video, normalized, ratio)
        normalized_paths.append(normalized)
        durations.append(await probe_video_duration_sec(normalized))
        if on_progress:
            on_progress(10 + round(((i + 1) / len(videos)) * 50))
    list_path = Path(f"{dest}.list.txt")
    list_content = "\n".join(f"file '{ffmpeg_path(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'" for p in normalized_paths)
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
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(dest),
        ]
    )
    if on_progress:
        on_progress(80)
    return {"outputPath": str(dest), "totalDurationSec": sum(durations)}


async def mix_background_music(video_path: str, music_path: str, output_path: str, video_duration_sec: float) -> str:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fade_out_start = max(video_duration_sec - 2.5, 1)
    with_audio = await has_audio_stream(video_path)
    args = ["-y", "-i", video_path, "-stream_loop", "-1", "-i", music_path]
    if with_audio:
        filt = (
            f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.28,"
            f"afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out_start:.2f}:d=2[music];"
            "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[va];"
            "[va][music]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
        args.extend(["-filter_complex", filt, "-map", "0:v:0", "-map", "[a]"])
    else:
        filt = (
            f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.32,"
            f"afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out_start:.2f}:d=2[a]"
        )
        args.extend(["-filter_complex", filt, "-map", "0:v:0", "-map", "[a]"])
    args.extend(
        [
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-t",
            f"{video_duration_sec:.3f}",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    await run_ffmpeg(args)
    return str(dest)
