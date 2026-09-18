from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services import ai_video, stock_reel
from app.services.ai_video import produce_ai_or_static_scene
from app.services.stock_reel import (
    personalized_and_generic_stills,
    produce_scene_clip,
    resolve_personalized_still,
    style_reference_images,
    validate_local_reel_assets,
)
from app.services.story import load_story_template, resolve_local_video_path


EXPECTED_PAIRS = {
    1: ("images/founder_scene_1.jpg", "images/morning_home.jpg"),
    2: ("images/founder_scene_2.jpg", "images/design_studio.jpg"),
    3: ("images/founder_scene_3.jpg", "images/boutique.jpg"),
    4: ("images/founder_scene_4.jpg", "images/founder_studio.jpg"),
    5: ("images/founder_scene_5.jpg", "images/family_home.jpg"),
    6: ("images/founder_scene_6.jpg", "images/city_view.jpg"),
}


class LocalReelAssetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.story = await load_story_template()
        self.by_id = {scene["sceneId"]: scene for scene in self.story["scenes"]}

    def test_scene_1_local_video_exists(self) -> None:
        scene = self.by_id[1]
        self.assertEqual(scene.get("localVideo"), "videos/scene-1.mp4")
        path = resolve_local_video_path(scene)
        self.assertTrue(path.is_file(), f"missing local AI clip: {path}")

    def test_other_scenes_have_no_local_video(self) -> None:
        for scene_id in (2, 3, 4, 5, 6):
            self.assertFalse((self.by_id[scene_id].get("localVideo") or "").strip())

    def test_each_scene_pairs_personalized_founder_with_first_style(self) -> None:
        for scene_id, (personalized, generic) in EXPECTED_PAIRS.items():
            picked = personalized_and_generic_stills(self.by_id[scene_id])
            self.assertEqual([item["file"] for item in picked], [personalized, generic])
            self.assertEqual(picked[0]["role"], "personalized_still")
            self.assertEqual(picked[1]["role"], "style_reference")
            self.assertNotIn("subject_reference.jpg", [item["file"] for item in picked])
            self.assertNotIn("customer_reference.png", [item["file"] for item in picked])
            self.assertNotIn("family_reference.png", [item["file"] for item in picked])

    def test_mixed_preflight_skips_scene_1_stills_and_requires_local_video(self) -> None:
        validate_local_reel_assets(self.story["scenes"], "mixed")
        validate_local_reel_assets(self.story["scenes"], "images_only")

    def test_personalized_still_hard_fails_when_file_missing(self) -> None:
        scene = dict(self.by_id[2])
        scene["personalizedStill"] = "images/founder_scene_missing.jpg"
        with self.assertRaises(RuntimeError) as ctx:
            resolve_personalized_still(scene)
        self.assertIn("missing on disk", str(ctx.exception))

    def test_personalized_still_rejects_subject_reference(self) -> None:
        scene = dict(self.by_id[1])
        scene["personalizedStill"] = "images/subject_reference.jpg"
        with self.assertRaises(RuntimeError) as ctx:
            resolve_personalized_still(scene)
        self.assertIn("subject_reference.jpg", str(ctx.exception))

    def test_personalized_still_hard_fails_when_unmapped(self) -> None:
        scene = dict(self.by_id[3])
        scene["personalizedStill"] = ""
        with self.assertRaises(RuntimeError) as ctx:
            resolve_personalized_still(scene)
        self.assertIn("missing personalizedStill", str(ctx.exception))

    def test_style_reference_excludes_non_style_roles(self) -> None:
        refs = [
            {"file": "subject.jpg", "role": "subject_identity"},
            {"file": "customer.png", "role": "customer_identity"},
            {"file": "style.jpg", "role": "style_reference"},
            {"file": "family.png", "role": "family_member_identity"},
        ]
        self.assertEqual([item["file"] for item in style_reference_images(refs)], ["style.jpg"])

    def test_generic_hard_fails_when_style_file_missing(self) -> None:
        scene = dict(self.by_id[2])
        scene["referenceImages"] = [{"file": "images/does-not-exist.jpg", "role": "style_reference", "promptLabel": "x"}]
        with self.assertRaises(RuntimeError) as ctx:
            personalized_and_generic_stills(scene)
        self.assertIn("missing on disk", str(ctx.exception))

    def test_stock_reel_does_not_call_seedance_or_stock_search(self) -> None:
        source = inspect.getsource(stock_reel)
        self.assertNotIn("generate_seedance", source)
        self.assertNotIn("search_stock", source)
        self.assertNotIn("download_stock_candidate", source)

    def test_ai_video_path_still_uses_seedance_and_reference_images_only(self) -> None:
        source = inspect.getsource(ai_video)
        self.assertIn("generate_seedance_video", source)
        self.assertIn("referenceImagePaths", source)
        self.assertNotIn("personalizedStill", source)

    def test_images_only_preflight_fails_if_a_founder_still_is_missing(self) -> None:
        scenes = [dict(scene) for scene in self.story["scenes"]]
        scenes[0]["personalizedStill"] = "images/founder_scene_missing.jpg"
        with self.assertRaises(RuntimeError):
            validate_local_reel_assets(scenes, "images_only")

    def test_mixed_preflight_still_fails_if_scene_2_founder_still_is_missing(self) -> None:
        scenes = [dict(scene) for scene in self.story["scenes"]]
        scenes[1]["personalizedStill"] = "images/founder_scene_missing.jpg"
        with self.assertRaises(RuntimeError):
            validate_local_reel_assets(scenes, "mixed")

    def test_mixed_preflight_uses_stills_when_local_video_missing(self) -> None:
        scenes = [dict(scene) for scene in self.story["scenes"]]
        scenes[0]["localVideo"] = "videos/does-not-exist.mp4"
        validate_local_reel_assets(scenes, "mixed")

    def test_mixed_preflight_fails_when_local_video_and_stills_missing(self) -> None:
        scenes = [dict(scene) for scene in self.story["scenes"]]
        scenes[0]["localVideo"] = "videos/does-not-exist.mp4"
        scenes[0]["personalizedStill"] = "images/founder_scene_missing.jpg"
        with self.assertRaises(RuntimeError) as ctx:
            validate_local_reel_assets(scenes, "mixed")
        self.assertIn("missing on disk", str(ctx.exception))

    def test_ai_video_reel_does_not_hard_fail_missing_byteplus_key_upfront(self) -> None:
        source = inspect.getsource(ai_video.generate_ai_video_reel)
        self.assertNotIn("BYTEPLUS_API_KEY not set", source)
        self.assertIn("produce_ai_or_static_scene", source)

    async def test_ai_scene_falls_back_to_stills_when_byteplus_key_missing(self) -> None:
        stills = AsyncMock(
            return_value={"path": "/tmp/out.mp4", "mediaType": "stock_image", "source": "local:a+b"}
        )
        with (
            patch("app.services.ai_video.byteplus_api_key", return_value=""),
            patch("app.services.ai_video.generate_seedance_video", new_callable=AsyncMock) as seedance,
            patch("app.services.ai_video.bake_two_local_stills", stills),
            patch("app.services.ai_video.scene_video_path", return_value=Path("/tmp/video.mp4")),
        ):
            result = await produce_ai_or_static_scene("s", "r", "sc", self.by_id[1], self.story, 10)
        seedance.assert_not_called()
        stills.assert_awaited_once()
        self.assertEqual(result["mediaType"], "stock_image")
        self.assertEqual(result["source"], "fallback:local:a+b")

    async def test_ai_scene_falls_back_to_stills_when_seedance_raises(self) -> None:
        stills = AsyncMock(
            return_value={"path": "/tmp/out.mp4", "mediaType": "stock_image", "source": "local:a+b"}
        )
        with (
            patch("app.services.ai_video.byteplus_api_key", return_value="fake-key"),
            patch(
                "app.services.ai_video.generate_seedance_video",
                AsyncMock(side_effect=RuntimeError("timeout")),
            ),
            patch("app.services.ai_video.bake_two_local_stills", stills),
            patch("app.services.ai_video.scene_video_path", return_value=Path("/tmp/video.mp4")),
        ):
            result = await produce_ai_or_static_scene("s", "r", "sc", self.by_id[2], self.story, 10)
        stills.assert_awaited_once()
        self.assertEqual(result["source"], "fallback:local:a+b")

    async def test_ai_scene_uses_seedance_when_key_and_output_exist(self) -> None:
        out = Path(tempfile.mkdtemp()) / "video.mp4"
        out.write_bytes(b"ok")
        seedance = AsyncMock()
        stills = AsyncMock()
        with (
            patch("app.services.ai_video.byteplus_api_key", return_value="fake-key"),
            patch("app.services.ai_video.generate_seedance_video", seedance),
            patch("app.services.ai_video.bake_two_local_stills", stills),
            patch("app.services.ai_video.scene_video_path", return_value=out),
        ):
            result = await produce_ai_or_static_scene("s", "r", "sc", self.by_id[1], self.story, 10)
        seedance.assert_awaited_once()
        stills.assert_not_called()
        self.assertEqual(result["mediaType"], "ai_video")
        self.assertEqual(result["source"], "seedance")
        self.assertEqual(result["path"], str(out))

    async def test_ai_scene_raises_when_seedance_and_stills_fail(self) -> None:
        with (
            patch("app.services.ai_video.byteplus_api_key", return_value="fake-key"),
            patch(
                "app.services.ai_video.generate_seedance_video",
                AsyncMock(side_effect=RuntimeError("timeout")),
            ),
            patch(
                "app.services.ai_video.bake_two_local_stills",
                AsyncMock(side_effect=RuntimeError("no stills")),
            ),
            patch("app.services.ai_video.scene_video_path", return_value=Path("/tmp/video.mp4")),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await produce_ai_or_static_scene("s", "r", "sc", self.by_id[3], self.story, 10)
        self.assertIn("timeout", str(ctx.exception))
        self.assertIn("no stills", str(ctx.exception))
        self.assertIn("static fallback failed", str(ctx.exception))

    async def test_mixed_scene_falls_back_to_stills_when_local_video_fails(self) -> None:
        stills = AsyncMock(
            return_value={"path": "/tmp/out.mp4", "mediaType": "stock_image", "source": "local:a+b"}
        )
        with (
            patch(
                "app.services.stock_reel.bake_local_video",
                AsyncMock(side_effect=RuntimeError("clip missing")),
            ),
            patch("app.services.stock_reel.bake_two_local_stills", stills),
            patch("app.services.stock_reel.scene_video_path", return_value=Path("/tmp/video.mp4")),
        ):
            result = await produce_scene_clip("s", "r", "sc", dict(self.by_id[1]), "mixed", 10)
        stills.assert_awaited_once()
        self.assertEqual(result["mediaType"], "stock_image")
        self.assertEqual(result["source"], "fallback:local:a+b")

    async def test_mixed_scene_keeps_local_video_when_bake_succeeds(self) -> None:
        bake_video = AsyncMock(
            return_value={
                "path": "/tmp/out.mp4",
                "mediaType": "ai_video",
                "source": "local:videos/scene-1.mp4",
            }
        )
        stills = AsyncMock()
        with (
            patch("app.services.stock_reel.bake_local_video", bake_video),
            patch("app.services.stock_reel.bake_two_local_stills", stills),
            patch("app.services.stock_reel.scene_video_path", return_value=Path("/tmp/video.mp4")),
        ):
            result = await produce_scene_clip("s", "r", "sc", dict(self.by_id[1]), "mixed", 10)
        bake_video.assert_awaited_once()
        stills.assert_not_called()
        self.assertEqual(result["source"], "local:videos/scene-1.mp4")


if __name__ == "__main__":
    unittest.main()
