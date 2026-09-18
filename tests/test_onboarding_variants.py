from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from app.services.orchestrator import start_both_reels


def _session(answers: dict[str, Any] | str) -> dict[str, Any]:
    payload = answers if isinstance(answers, str) else json.dumps(answers)
    return {
        "session_id": "session-1",
        "device_id": "device-1",
        "onboarding_answers": payload,
        "status": "generating",
    }


class OnboardingVariantMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def _start(self, answers: dict[str, Any] | str) -> tuple[dict[str, str | None], list[str], int]:
        created: list[str] = []
        spawned = 0

        async def fake_create_reel(session_id: str, reel_type: str) -> dict[str, str]:
            created.append(reel_type)
            return {"reel_id": f"reel-{reel_type}"}

        def fake_spawn(coro) -> None:
            nonlocal spawned
            spawned += 1
            coro.close()

        with (
            patch("app.services.orchestrator.get_session", AsyncMock(return_value=_session(answers))),
            patch("app.services.orchestrator.create_reel", side_effect=fake_create_reel),
            patch("app.services.orchestrator._spawn", side_effect=fake_spawn),
            patch("app.services.orchestrator.generate_ai_video_reel", new_callable=AsyncMock) as gen_ai,
            patch("app.services.orchestrator.generate_stock_media_reel", new_callable=AsyncMock) as gen_stock,
        ):
            result = await start_both_reels("session-1")
        gen_ai.assert_not_called()
        gen_stock.assert_not_called()
        return result, created, spawned

    def _assert_started(self, created: list[str], expected: list[str], spawned: int) -> None:
        self.assertEqual(created, expected)
        self.assertEqual(spawned, len(expected))

    async def test_missing_reel_variants_starts_ai_and_mixed(self) -> None:
        result, created, spawned = await self._start({"voice": "aria"})
        self._assert_started(created, ["ai_video", "stock_media"], spawned)
        self.assertEqual(result["aiReelId"], "reel-ai_video")
        self.assertEqual(result["stockReelId"], "reel-stock_media")
        self.assertNotIn("imagesReelId", result)

    async def test_empty_reel_variants_starts_ai_and_mixed(self) -> None:
        result, created, spawned = await self._start({"reel_variants": []})
        self._assert_started(created, ["ai_video", "stock_media"], spawned)
        self.assertNotIn("imagesReelId", result)

    async def test_images_only_starts_only_images_pipeline(self) -> None:
        result, created, spawned = await self._start({"reel_variants": ["images_only"]})
        self._assert_started(created, ["images_only"], spawned)
        self.assertEqual(result, {"imagesReelId": "reel-images_only"})

    async def test_mixed_and_images_only_start_those_two(self) -> None:
        result, created, spawned = await self._start({"reel_variants": ["mixed", "images_only"]})
        self._assert_started(created, ["stock_media", "images_only"], spawned)
        self.assertNotIn("aiReelId", result)
        self.assertEqual(result["stockReelId"], "reel-stock_media")
        self.assertEqual(result["imagesReelId"], "reel-images_only")

    async def test_all_three_variants_start_all_pipelines(self) -> None:
        result, created, spawned = await self._start(
            {"reel_variants": ["ai_video", "mixed", "images_only"]}
        )
        self._assert_started(created, ["ai_video", "stock_media", "images_only"], spawned)
        self.assertEqual(
            result,
            {
                "aiReelId": "reel-ai_video",
                "stockReelId": "reel-stock_media",
                "imagesReelId": "reel-images_only",
            },
        )

    async def test_non_list_reel_variants_uses_default_ai_and_mixed(self) -> None:
        result, created, spawned = await self._start({"reel_variants": "mixed"})
        self._assert_started(created, ["ai_video", "stock_media"], spawned)
        self.assertNotIn("imagesReelId", result)

    async def test_unknown_variants_only_start_nothing(self) -> None:
        result, created, spawned = await self._start({"reel_variants": ["bogus", "stock_media"]})
        self._assert_started(created, [], spawned)
        self.assertEqual(result, {})

    async def test_unknown_variants_are_ignored_among_valid_ones(self) -> None:
        result, created, spawned = await self._start(
            {"reel_variants": ["mixed", "not-a-type", "images_only"]}
        )
        self._assert_started(created, ["stock_media", "images_only"], spawned)
        self.assertNotIn("aiReelId", result)

    async def test_invalid_json_answers_uses_default_ai_and_mixed(self) -> None:
        result, created, spawned = await self._start("{not-json")
        self._assert_started(created, ["ai_video", "stock_media"], spawned)
        self.assertNotIn("imagesReelId", result)


if __name__ == "__main__":
    unittest.main()
