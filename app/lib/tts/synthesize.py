from __future__ import annotations

import logging
from pathlib import Path

import edge_tts

from app.config import config
from app.lib.onboarding_catalog import edge_voice_from_catalog
from app.lib.tts.edge_ws import synthesize_edge_ws

logger = logging.getLogger(__name__)


def edge_voice_for(voice_id: str | None) -> str:
    if not voice_id:
        return config.default_edge_voice
    if "Neural" in voice_id:
        return voice_id
    return edge_voice_from_catalog(voice_id) or config.default_edge_voice


async def synthesize_affirmation(text: str, voice_id: str | None, output_path: str | Path) -> dict[str, str]:
    cleaned = text.strip()
    if not cleaned:
        raise RuntimeError("Affirmation text is empty")
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    voice = edge_voice_for(voice_id)
    try:
        communicate = edge_tts.Communicate(cleaned, voice)
        await communicate.save(str(dest))
        return {"audioPath": str(dest), "voice": voice}
    except Exception as err:
        logger.warning("edge-tts failed (%s); falling back to Edge WebSocket", err)
        await synthesize_edge_ws(cleaned, voice, dest)
        return {"audioPath": str(dest), "voice": voice}
