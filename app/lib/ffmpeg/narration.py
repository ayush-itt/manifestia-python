from __future__ import annotations

from pathlib import Path

from app.lib.ffmpeg.assembly import probe_video_duration_sec, run_ffmpeg


async def pad_scene_narration(speech_path: str | Path, output_path: str | Path, scene_duration_sec: float, delay_sec: float) -> str:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    delay_ms = max(0, round(delay_sec * 1000))
    hold = max(scene_duration_sec, 0.1)
    af = (
        f"adelay={delay_ms}:all=1,apad=whole_dur={hold:.3f}"
        if delay_ms > 0
        else f"apad=whole_dur={hold:.3f}"
    )
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(speech_path),
            "-af",
            af,
            "-t",
            f"{hold:.3f}",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(dest),
        ]
    )
    return str(dest)


async def concat_audio_files(paths: list[str], output_path: str | Path) -> str:
    if len(paths) == 1:
        return paths[0]
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["-y"]
    for path in paths:
        args.extend(["-i", path])
    concat = f"{''.join(f'[{i}:a]' for i in range(len(paths)))}concat=n={len(paths)}:v=0:a=1[a]"
    args.extend(["-filter_complex", concat, "-map", "[a]", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(dest)])
    await run_ffmpeg(args)
    return str(dest)


async def mix_speech_and_music(speech_path: str | Path, music_path: str | Path, output_path: str | Path) -> str:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        speech_len = await probe_video_duration_sec(speech_path)
    except Exception:
        speech_len = 60
    fade_out_start = max(speech_len - 2, 0.2)
    duck = (
        "[1:a]aloop=loop=-1:size=2e+09,volume=0.22,afade=t=in:st=0:d=2[bg];"
        "[0:a]asplit=2[speech][key];"
        "[bg][key]sidechaincompress=threshold=0.04:ratio=8:attack=200:release=500[ducked];"
        f"[speech][ducked]amix=inputs=2:duration=first:dropout_transition=2,"
        f"afade=t=out:st={fade_out_start:.3f}:d=2,loudnorm=I=-16:LRA=11:TP=-1.5[aout]"
    )
    simple = (
        f"[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2:weights=1 0.18,"
        f"afade=t=out:st={fade_out_start:.3f}:d=2[aout]"
    )
    encode = ["-map", "[aout]", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-t", f"{speech_len:.3f}", str(dest)]
    try:
        await run_ffmpeg(["-y", "-i", str(speech_path), "-i", str(music_path), "-filter_complex", duck, *encode])
    except Exception:
        await run_ffmpeg(
            [
                "-y",
                "-i",
                str(speech_path),
                "-stream_loop",
                "-1",
                "-i",
                str(music_path),
                "-filter_complex",
                simple,
                *encode,
            ]
        )
    return str(dest)


async def mux_video_with_audio(video_path: str | Path, audio_path: str | Path, output_path: str | Path) -> str:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    return str(dest)
