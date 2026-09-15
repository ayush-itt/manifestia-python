from __future__ import annotations

import json
from typing import Any

from app.config import config


def load_onboarding_catalog() -> dict[str, Any]:
    raw = json.loads(config.onboarding_catalog_path.read_text(encoding="utf-8"))
    voices = raw.get("voices") if isinstance(raw, dict) else None
    return {**raw, "voices": voices if isinstance(voices, list) else []}


def edge_voice_from_catalog(voice_id: str) -> str | None:
    wanted = voice_id.strip().lower()
    for voice in load_onboarding_catalog().get("voices") or []:
        if not isinstance(voice, dict):
            continue
        if str(voice.get("id") or "").strip().lower() != wanted:
            continue
        edge = str(voice.get("edge_voice") or "").strip()
        return edge or None
    return None
