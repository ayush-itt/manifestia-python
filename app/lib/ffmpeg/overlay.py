from __future__ import annotations

from pathlib import Path

from app.config import config
from app.lib.ffmpeg.assembly import has_audio_stream, run_ffmpeg


def overlay_font() -> str:
    candidates = [
        Path("C:/Windows/Fonts/georgia.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]
    found = next((p for p in candidates if p.exists()), candidates[1])
    return str(found).replace("\\", "/").replace(":", "\\:")


def wrap_affirmation(text: str, max_chars: int = 28) -> str:
    words = [w for w in text.strip().split() if w]
    lines: list[str] = []
    current = ""
    for word in words:
        nxt = f"{current} {word}" if current else word
        if len(nxt) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = nxt
    if current:
        lines.append(current)
    return "\n".join(lines[:5])


def ffmpeg_filter_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


async def _write_overlay_png(dest: str | Path, text_file: str | Path, width: int, height: int) -> None:
    font = overlay_font()
    font_size = 38 if height > width else 44
    draw = (
        f"drawtext=fontfile='{font}':textfile='{ffmpeg_filter_path(text_file)}':"
        f"fontcolor=0xFFFFFF:fontsize={font_size}:line_spacing=4:"
        "borderw=2:bordercolor=black@0.80:"
        "shadowcolor=black@0.85:shadowx=2:shadowy=3:"
        "x=(w-text_w)/2:y=(h-th-72)"
    )
    await run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black@0.0:s={width}x{height}:d=1,format=rgba",
            "-vf",
            draw,
            "-frames:v",
            "1",
            "-update",
            "1",
            str(dest),
        ]
    )


async def burn_affirmation_overlay(
    video_path: str | Path,
    output_path: str | Path,
    text: str,
    duration_sec: float,
    *,
    caption_start: float,
    fade_in_sec: float,
    fade_out_start: float,
    fade_out_sec: float,
) -> str:
    affirmation = wrap_affirmation(text)
    if not affirmation:
        return str(video_path)
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    text_file = Path(f"{dest}.affirmation.txt")
    png_path = Path(f"{dest}.overlay.png")
    text_file.write_text(affirmation, encoding="utf-8")
    await _write_overlay_png(png_path, text_file, config.video_width, config.video_height)

    graph = (
        f"[1:v]format=rgba,fade=t=in:st={caption_start:.2f}:d={fade_in_sec:.2f}:alpha=1,"
        f"fade=t=out:st={fade_out_start:.2f}:d={fade_out_sec:.2f}:alpha=1[ov];"
        "[0:v][ov]overlay=0:0:shortest=1[vout]"
    )
    encode = [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(config.video_fps),
        "-fps_mode",
        "cfr",
        "-t",
        str(duration_sec),
        str(dest),
    ]
    if await has_audio_stream(video_path):
        await run_ffmpeg(
            [
                "-y",
                "-i",
                str(video_path),
                "-loop",
                "1",
                "-i",
                str(png_path),
                "-filter_complex",
                graph,
                "-map",
                "[vout]",
                "-map",
                "0:a:0",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-shortest",
                *encode,
            ]
        )
    else:
        await run_ffmpeg(
            [
                "-y",
                "-i",
                str(video_path),
                "-loop",
                "1",
                "-i",
                str(png_path),
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-filter_complex",
                graph,
                "-map",
                "[vout]",
                "-map",
                "2:a:0",
                "-c:a",
                "aac",
                "-shortest",
                *encode,
            ]
        )
    return str(dest)
