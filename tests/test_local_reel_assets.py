from __future__ import annotations

import inspect
import unittest

from app.services import ai_video, stock_reel
from app.services.stock_reel import (
    personalized_and_generic_stills,
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


if __name__ == "__main__":
    unittest.main()
