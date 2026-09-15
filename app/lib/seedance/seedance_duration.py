from __future__ import annotations

from typing import Literal

SeedanceDurationSec = Literal[5, 10]
VALID: tuple[int, ...] = (5, 10)


def assert_seedance_duration(duration_sec: float) -> SeedanceDurationSec:
    if duration_sec in (5, 10):
        return int(duration_sec)  # type: ignore[return-value]
    raise RuntimeError(f"Invalid Seedance duration {duration_sec}; must be 5 or 10")


def is_valid_seedance_duration(duration_sec: float) -> bool:
    return duration_sec in VALID
