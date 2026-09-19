from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.lib.ffmpeg.assembly import assemble_reel, matches_reel_geometry, _parse_frame_rate
from app.lib.ffmpeg.overlay import burn_affirmation_overlay
from app.services.stock_reel import concat_silent_clips


class GeometryTests(unittest.TestCase):
    def test_parse_frame_rate_fraction(self) -> None:
        self.assertAlmostEqual(_parse_frame_rate("24/1"), 24.0)
        self.assertAlmostEqual(_parse_frame_rate("24000/1001"), 23.976, places=3)

    def test_portrait_24fps_matches(self) -> None:
        self.assertTrue(matches_reel_geometry(720, 1280, 24.0, "9:16"))
        self.assertFalse(matches_reel_geometry(1280, 720, 24.0, "9:16"))
        self.assertFalse(matches_reel_geometry(720, 1280, 30.0, "9:16"))


class ConcatCopyTests(unittest.IsolatedAsyncioTestCase):
    async def test_concat_silent_clips_uses_stream_copy(self) -> None:
        captured: list[list[str]] = []

        async def fake_run(args: list[str]) -> None:
            captured.append(args)

        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "joined.mp4")
            with patch("app.services.stock_reel.run_ffmpeg", fake_run):
                await concat_silent_clips([str(Path(tmp) / "a.mp4"), str(Path(tmp) / "b.mp4")], out)
        self.assertEqual(len(captured), 1)
        self.assertIn("-c", captured[0])
        self.assertEqual(captured[0][captured[0].index("-c") + 1], "copy")
        self.assertNotIn("libx264", captured[0])

    async def test_assemble_skips_normalize_when_already_matching(self) -> None:
        captured: list[list[str]] = []

        async def fake_run(args: list[str]) -> None:
            captured.append(args)

        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp) / "scene.mp4"
            scene.write_bytes(b"fake")
            out = Path(tmp) / "reel.mp4"
            with (
                patch("app.lib.ffmpeg.assembly.probe_video_geometry", AsyncMock(return_value=(720, 1280, 24.0))),
                patch("app.lib.ffmpeg.assembly.probe_video_duration_sec", AsyncMock(return_value=10.0)),
                patch("app.lib.ffmpeg.assembly.normalize_scene_video", AsyncMock()) as normalize,
                patch("app.lib.ffmpeg.assembly.run_ffmpeg", fake_run),
            ):
                result = await assemble_reel("9:16", [str(scene)], out)
            normalize.assert_not_awaited()
        self.assertEqual(result["totalDurationSec"], 10.0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][captured[0].index("-c") + 1], "copy")
        self.assertNotIn("libx264", captured[0])

    async def test_overlay_uses_veryfast_crf18(self) -> None:
        captured: list[list[str]] = []

        async def fake_run(args: list[str]) -> None:
            captured.append(args)

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "in.mp4"
            video.write_bytes(b"fake")
            out = Path(tmp) / "out.mp4"
            with (
                patch("app.lib.ffmpeg.overlay.has_audio_stream", AsyncMock(return_value=True)),
                patch("app.lib.ffmpeg.overlay.run_ffmpeg", fake_run),
            ):
                await burn_affirmation_overlay(
                    video,
                    out,
                    "I am wealthy and calm.",
                    10.0,
                    caption_start=0.2,
                    fade_in_sec=0.3,
                    fade_out_start=8.5,
                    fade_out_sec=0.4,
                )
        encode = captured[-1]
        self.assertIn("-preset", encode)
        self.assertEqual(encode[encode.index("-preset") + 1], "veryfast")
        self.assertEqual(encode[encode.index("-crf") + 1], "18")


if __name__ == "__main__":
    unittest.main()
