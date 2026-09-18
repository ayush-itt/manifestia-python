from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import numpy as np

from app.lib.ffmpeg.assembly import _popen_kwargs, _run_exec

KENBURNS_DURATION_S = 12
KENBURNS_ZOOM = 0.12
KENBURNS_TX = 0.02
KENBURNS_TY = 0.01


def kenburns_eased(frame_index: int, fps: int) -> float:
    one = max(round(KENBURNS_DURATION_S * fps), 1)
    period = one * 2
    phase = frame_index % period
    local = phase / one if phase < one else 2 - phase / one
    return 0.5 - 0.5 * np.cos(np.pi * local)


def remap_kenburns_frame(src: np.ndarray, width: int, height: int, eased: float, sign: int) -> np.ndarray:
    src_img = src.reshape((height, width, 3)).astype(np.float32)
    zoom = 1 + KENBURNS_ZOOM * eased
    ox = sign * width * KENBURNS_TX * eased
    oy = sign * height * KENBURNS_TY * eased
    cx = width / 2
    cy = height / 2
    ys, xs = np.indices((height, width), dtype=np.float32)
    src_x = (xs - cx) / zoom + cx + ox
    src_y = (ys - cy) / zoom + cy + oy
    x0 = np.floor(src_x).astype(np.int32)
    y0 = np.floor(src_y).astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1
    wx = (src_x - x0)[..., None]
    wy = (src_y - y0)[..., None]
    x0c = np.clip(x0, 0, width - 1)
    x1c = np.clip(x1, 0, width - 1)
    y0c = np.clip(y0, 0, height - 1)
    y1c = np.clip(y1, 0, height - 1)
    w00 = (1 - wx) * (1 - wy)
    w10 = wx * (1 - wy)
    w01 = (1 - wx) * wy
    w11 = wx * wy
    out = src_img[y0c, x0c] * w00 + src_img[y0c, x1c] * w10 + src_img[y1c, x0c] * w01 + src_img[y1c, x1c] * w11
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


async def decode_image_rgb24(image_path: str | Path, width: int, height: int) -> bytes:
    expected = width * height * 3
    args = [
        "-v",
        "error",
        "-i",
        str(image_path),
        "-vf",
        f"scale={width}:{height}:flags=lanczos",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-frames:v",
        "1",
        "pipe:1",
    ]
    proc = await asyncio.to_thread(_run_exec, "ffmpeg", args)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg decode exited {proc.returncode}: {proc.stderr.decode('utf-8', errors='replace')[-800:]}"
        )
    if len(proc.stdout) != expected:
        raise RuntimeError(f"Ken Burns still decode size mismatch: got {len(proc.stdout)}, expected {expected}")
    return proc.stdout


def _encode_rgb24_kenburns_sync(
    src: bytes,
    output_path: str,
    width: int,
    height: int,
    fps: int,
    frames: int,
    sign: int,
) -> None:
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-frames:v",
            str(frames),
            "-an",
            "-movflags",
            "+faststart",
            output_path,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **_popen_kwargs(),
    )
    assert proc.stdin is not None
    src_arr = np.frombuffer(src, dtype=np.uint8).copy()
    try:
        for n in range(frames):
            frame = remap_kenburns_frame(src_arr, width, height, kenburns_eased(n, fps), sign)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except Exception:
        proc.kill()
        raise
    stderr = proc.stderr.read() if proc.stderr else b""
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg kenburns exited {rc}: {stderr.decode('utf-8', errors='replace')[-800:]}")


async def encode_rgb24_kenburns(
    src: bytes,
    output_path: str | Path,
    width: int,
    height: int,
    fps: int,
    frames: int,
    sign: int,
) -> None:
    await asyncio.to_thread(
        _encode_rgb24_kenburns_sync,
        src,
        str(output_path),
        width,
        height,
        fps,
        frames,
        sign,
    )
