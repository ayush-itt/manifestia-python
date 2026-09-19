from __future__ import annotations

import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from app.lib.ffmpeg.assembly import run_command, run_ffmpeg
from app.lib.ffmpeg.kenburns import (
    KENBURNS_TX,
    KENBURNS_TY,
    KENBURNS_ZOOM,
    kenburns_filter,
    render_kenburns_ffmpeg,
)

STUDIO_STILL = Path(__file__).resolve().parents[1] / "content" / "story" / "images" / "founder_studio.jpg"


class KenBurnsFilterTests(unittest.TestCase):
    def test_portrait_graph_keeps_ease_zoom_and_output_size(self) -> None:
        vf = kenburns_filter(720, 1280, 120, 1, fps=24)
        self.assertIn("0.5-0.5*cos(PI*n/119)", vf)
        self.assertIn(f"1+{KENBURNS_ZOOM}*", vf)
        self.assertIn("scale=864:1536", vf)
        self.assertIn("scale=720:1280:flags=lanczos", vf)
        self.assertIn("loop=119:1:0", vf)
        self.assertIn("setpts=N/24/TB", vf)
        self.assertNotIn("fps=24", vf)
        self.assertIn(f"iw*{KENBURNS_TX}*", vf)
        self.assertIn(f"ih*{KENBURNS_TY}*", vf)
        self.assertIn("(1)*iw", vf)

    def test_odd_scene_index_reverses_pan(self) -> None:
        vf = kenburns_filter(720, 1280, 120, -1, fps=24)
        self.assertIn("(-1)*iw", vf)
        self.assertIn("(-1)*ih", vf)


class KenBurnsMotionTests(unittest.IsolatedAsyncioTestCase):
    async def test_five_second_clip_first_and_last_frames_differ(self) -> None:
        if not STUDIO_STILL.is_file():
            self.skipTest(f"missing still: {STUDIO_STILL}")
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "kb.mp4"
            first = Path(tmp) / "first.png"
            last = Path(tmp) / "last.png"
            started = time.perf_counter()
            await render_kenburns_ffmpeg(STUDIO_STILL, clip, 720, 1280, "ken-burns", 5.0, 24, 1)
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 5.0, f"Ken Burns encode too slow: {elapsed:.2f}s")
            await run_ffmpeg(["-y", "-i", str(clip), "-vf", "select=eq(n\\,0)", "-frames:v", "1", str(first)])
            await run_ffmpeg(["-y", "-i", str(clip), "-vf", "select=eq(n\\,119)", "-frames:v", "1", str(last)])
            first_hash = hashlib.sha256(first.read_bytes()).hexdigest()
            last_hash = hashlib.sha256(last.read_bytes()).hexdigest()
            self.assertNotEqual(first_hash, last_hash, "first and last frames are identical; zoom is frozen")
            _, stderr = await run_command(
                "ffmpeg",
                ["-i", str(first), "-i", str(last), "-filter_complex", "psnr", "-f", "null", "-"],
            )
            self.assertNotIn("psnr_avg:inf", stderr.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
