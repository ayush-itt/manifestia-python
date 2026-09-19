from __future__ import annotations

import unittest

from app.lib.timing import (
    CAPTION_FADE_IN_SEC,
    CAPTION_LEAD_SEC,
    caption_fade_times,
    centered_voice_delay,
)


class CenteredVoiceDelayTests(unittest.TestCase):
    def test_centers_six_second_audio_in_ten_second_scene(self) -> None:
        self.assertEqual(centered_voice_delay(10, 6), 2.0)

    def test_centers_eight_second_audio(self) -> None:
        self.assertEqual(centered_voice_delay(10, 8), 1.0)

    def test_full_length_audio_has_no_delay(self) -> None:
        self.assertEqual(centered_voice_delay(10, 10), 0.0)

    def test_clamps_overlong_audio(self) -> None:
        self.assertEqual(centered_voice_delay(10, 12), 0.0)

    def test_clamps_negative_audio(self) -> None:
        self.assertEqual(centered_voice_delay(10, -1), 5.0)


class CaptionFadeTimesTests(unittest.TestCase):
    def test_six_second_line_fades_in_before_centered_voice(self) -> None:
        delay = centered_voice_delay(10, 6)
        timings = caption_fade_times(10, delay, 6)
        self.assertAlmostEqual(delay, 2.0)
        self.assertAlmostEqual(timings["caption_start"], 1.45)
        self.assertAlmostEqual(timings["fade_in_sec"], CAPTION_FADE_IN_SEC)
        self.assertLess(timings["caption_start"] + timings["fade_in_sec"], delay)
        self.assertAlmostEqual(timings["caption_start"] + timings["fade_in_sec"] + CAPTION_LEAD_SEC, delay)
        self.assertGreaterEqual(timings["fade_out_start"], timings["voice_end_sec"])
        self.assertLessEqual(timings["fade_out_start"] + timings["fade_out_sec"], 10)

    def test_fade_in_completes_before_voice_when_delay_allows(self) -> None:
        for audio in (4.0, 6.0, 8.0):
            delay = centered_voice_delay(10, audio)
            timings = caption_fade_times(10, delay, audio)
            self.assertLessEqual(timings["caption_start"] + timings["fade_in_sec"], delay + 1e-9)

    def test_short_delay_shortens_fade_in_and_starts_at_zero(self) -> None:
        timings = caption_fade_times(10, 0.3, 9.4)
        self.assertEqual(timings["caption_start"], 0.0)
        self.assertLessEqual(timings["fade_in_sec"], 0.3)
        self.assertLessEqual(timings["caption_start"] + timings["fade_in_sec"], 0.3 + 1e-9)

    def test_zero_delay_starts_caption_immediately(self) -> None:
        timings = caption_fade_times(10, 0.0, 10)
        self.assertEqual(timings["caption_start"], 0.0)
        self.assertLess(timings["fade_in_sec"], CAPTION_FADE_IN_SEC)


if __name__ == "__main__":
    unittest.main()
