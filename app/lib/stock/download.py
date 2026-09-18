from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.types import StockCandidate

logger = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CLIP_TIMEOUT_MS = 20.0
MAX_CLIP_BYTES = 40 * 1024 * 1024


def download_headers(url: str, source: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "video/mp4,image/avif,image/webp,image/*,*/*;q=0.8",
    }
    if source == "pexels" or "pexels.com" in url:
        headers["Referer"] = "https://www.pexels.com/"
    elif source == "pixabay" or "pixabay.com" in url:
        headers["Referer"] = "https://pixabay.com/"
    elif source == "unsplash" or "unsplash.com" in url:
        headers["Referer"] = "https://unsplash.com/"
    return headers


async def download_url_to_file(
    url: str,
    dest_path: str | Path,
    headers: dict[str, str] | None = None,
    source: str | None = None,
) -> str:
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    hdrs = {**download_headers(url, source), **(headers or {})}
    last_error: Exception | None = None
    for insecure in (False, True):
        try:
            async with httpx.AsyncClient(follow_redirects=True, verify=not insecure, timeout=CLIP_TIMEOUT_MS) as client:
                async with client.stream("GET", url, headers=hdrs) as res:
                    if res.status_code >= 400:
                        raise RuntimeError(f"Download failed {res.status_code} for {res.url}")
                    declared = int(res.headers.get("content-length") or 0)
                    if declared > MAX_CLIP_BYTES:
                        raise RuntimeError(f"clip too large: {declared} bytes")
                    written = 0
                    with dest.open("wb") as handle:
                        async for chunk in res.aiter_bytes():
                            written += len(chunk)
                            if written > MAX_CLIP_BYTES:
                                raise RuntimeError(f"clip too large: {written} bytes")
                            handle.write(chunk)
            if insecure:
                logger.warning("saved with TLS verify off: %s", url[:120])
            return str(dest)
        except Exception as err:
            last_error = err
            kind = "insecure" if insecure else "secure"
            logger.warning("%s download failed: %s", kind, err)
    raise last_error if last_error else RuntimeError(f"Download failed for {url}")


def stock_file_extension(candidate: StockCandidate) -> str:
    from_url = (candidate["downloadUrl"].split("?")[0] or "").split(".")[-1].lower()
    if from_url in {"mp4", "mov", "webm", "jpg", "jpeg", "png", "webp"}:
        return "jpg" if from_url == "jpeg" else from_url
    return "mp4" if candidate["kind"] == "video" else "jpg"
