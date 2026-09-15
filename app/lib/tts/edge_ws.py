from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path

import websockets

TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
CHROMIUM_FULL_VERSION = "143.0.3650.75"
CHROMIUM_MAJOR_VERSION = CHROMIUM_FULL_VERSION.split(".")[0]
SEC_MS_GEC_VERSION = f"1-{CHROMIUM_FULL_VERSION}"
WIN_EPOCH = 11_644_473_600
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    f"Chrome/{CHROMIUM_MAJOR_VERSION}.0.0.0 Safari/537.36 Edg/{CHROMIUM_MAJOR_VERSION}.0.0.0"
)

_clock_skew_seconds = 0.0


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _ticks_to_ms(value: float) -> int:
    return max(0, round(value / 10_000))


def _generate_sec_ms_gec() -> str:
    ticks = time.time() + _clock_skew_seconds + WIN_EPOCH
    ticks -= ticks % 300
    ticks *= 10_000_000
    payload = f"{ticks:.0f}{TRUSTED_CLIENT_TOKEN}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest().upper()


def _apply_server_date(date_header: str | None) -> None:
    global _clock_skew_seconds
    if not date_header:
        return
    from email.utils import parsedate_to_datetime

    try:
        server = parsedate_to_datetime(date_header).timestamp()
    except Exception:
        return
    _clock_skew_seconds += server - (time.time() + _clock_skew_seconds)


def _connect_url(connection_id: str) -> str:
    gec = _generate_sec_ms_gec()
    return (
        "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"
        f"?TrustedClientToken={TRUSTED_CLIENT_TOKEN}"
        f"&ConnectionId={connection_id}"
        f"&Sec-MS-GEC={gec}"
        f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}"
    )


def _handshake_headers() -> dict[str, str]:
    return {
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Origin": "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold",
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": f"muid={uuid.uuid4().hex.upper()};",
    }


async def synthesize_edge_ws(text: str, voice: str, output_path: str | Path) -> dict[str, float | str]:
    global _clock_skew_seconds
    voice = voice or "en-US-AriaNeural"
    locale = "-".join(voice.split("-")[:2]) or "en-US"
    last_error: Exception | None = None
    audio_chunks: list[bytes] = []
    last_end_ms = 0

    for _attempt in range(2):
        request_id = uuid.uuid4().hex
        audio_chunks = []
        last_end_ms = 0
        ws_url = _connect_url(request_id)
        try:
            async with websockets.connect(
                ws_url,
                additional_headers=_handshake_headers(),
                max_size=None,
                open_timeout=20,
            ) as ws:
                config_msg = "\r\n".join(
                    [
                        f"X-Timestamp:{time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())}",
                        "Content-Type:application/json; charset=utf-8",
                        "Path:speech.config",
                        "",
                        json.dumps(
                            {
                                "context": {
                                    "synthesis": {
                                        "audio": {
                                            "metadataoptions": {
                                                "sentenceBoundaryEnabled": "false",
                                                "wordBoundaryEnabled": "true",
                                            },
                                            "outputFormat": "audio-24khz-48kbitrate-mono-mp3",
                                        }
                                    }
                                }
                            }
                        ),
                    ]
                )
                await ws.send(config_msg)
                ssml = (
                    f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{_escape_xml(locale)}">'
                    f'<voice name="{_escape_xml(voice)}">'
                    f'<prosody rate="+0%" pitch="+0Hz">{_escape_xml(text)}</prosody>'
                    "</voice></speak>"
                )
                ssml_msg = "\r\n".join(
                    [
                        f"X-RequestId:{request_id}",
                        "Content-Type:application/ssml+xml",
                        f"X-Timestamp:{time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())}Z",
                        "Path:ssml",
                        "",
                        ssml,
                    ]
                )
                await ws.send(ssml_msg)
                async with asyncio.timeout(60):
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            if len(raw) < 2:
                                continue
                            header_length = int.from_bytes(raw[:2], "big")
                            header = raw[2 : 2 + header_length].decode("utf-8", errors="replace")
                            body = raw[2 + header_length :]
                            if "Path:audio" in header:
                                audio_chunks.append(body)
                            continue
                        text_msg = str(raw)
                        if "Path:turn.end" in text_msg:
                            break
                        if "Path:audio.metadata" in text_msg:
                            json_start = text_msg.find("{")
                            if json_start < 0:
                                continue
                            try:
                                meta = json.loads(text_msg[json_start:])
                                for item in meta.get("Metadata") or []:
                                    if item.get("Type") != "WordBoundary":
                                        continue
                                    data = item.get("Data") or {}
                                    start = _ticks_to_ms(data.get("Offset") or 0)
                                    last_end_ms = start + _ticks_to_ms(data.get("Duration") or 0)
                            except json.JSONDecodeError:
                                pass
            last_error = None
            break
        except Exception as err:
            last_error = err
            status = getattr(err, "status_code", None) or getattr(err, "status", None)
            headers = getattr(err, "headers", None) or {}
            if hasattr(headers, "get"):
                _apply_server_date(headers.get("Date") or headers.get("date"))
            if status == 403:
                continue

    if last_error:
        raise last_error
    if not audio_chunks:
        raise RuntimeError("Edge TTS returned no audio")
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"".join(audio_chunks))
    return {"audioPath": str(dest), "voice": voice, "durationSec": last_end_ms / 1000}
