# Manifestia Python

Standalone dual-pipeline reel generator, ported from `manifestia-node/backend` to FastAPI + SQLite.

1. **AI video reel** — Seedance 2 generates each scene from `scenes[].prompt` + `referenceImages`. After clips download, the shared finish step burns affirmation text, Edge TTS, and background music.
2. **Mixed media** — `stockQuery` per scene (Pixabay/Coverr/Pexels clips on ~1/3 of scenes, Ken Burns stills on the rest)
3. **Images only** — `stockQuery` + Ken Burns stills

Content pack lives in `content/` (story prompts, reference stills, onboarding questions, voice catalog, and background music). Override with `STORY_*` / `BACKGROUND_MUSIC_DIR` / `ONBOARDING_*` env vars if needed.

| Path | Used by |
|---|---|
| `content/story/story.json` | AI uses `scenes[].prompt` + `referenceImages`. Mixed / images-only use `scenes[].stockQuery`. |
| `content/story/images/` | Seedance-ready reference stills and Ken Burns last-resort fallbacks |
| `content/onboarding/questions.json` | Interview questions |
| `content/onboarding/catalog.json` | Voices, life areas, and chips |
| `content/background-music/` | Local music catalog (hopeful plus related mood samples) |

## Stack

- Backend: Python 3.11–3.13 locally (Render image is **3.12**; do not use 3.14)
- FastAPI + SQLite + OpenAPI
- Auth: device ID only
- Requires `ffmpeg` and `ffprobe` on PATH

## Run

```bash
cd manifestia-python
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 4100
```

Put `BYTEPLUS_API_KEY` in `.env` before generating an AI video reel. **`.env` changes are not picked up by `--reload`** — stop uvicorn completely (Ctrl+C) and start it again. Startup logs print `BYTEPLUS_API_KEY: set | MISSING`; `/health` also reports `byteplusApiKey`.

A reel that already failed with `BYTEPLUS_API_KEY not set` keeps that error in SQLite until you regenerate or start a new session.

- Health: http://localhost:4100/health
- Swagger: http://localhost:4100/api-docs
- OpenAPI: http://localhost:4100/openapi.json
- FastAPI docs: http://localhost:4100/docs

Point the existing Node frontend at this backend (Vite already proxies `/api` and `/media` to port 4100):

```bash
cd manifestia-node/frontend
npm run dev
```

Wipe generated reels:

```bash
python -m scripts.clean_reels
python -m scripts.clean_reels --dry-run
python -m scripts.clean_reels --session <sessionId>
python -m scripts.clean_reels --reel <reelId>
```

To point the existing frontend at this backend, stop the Node server on port 4100, start this app on 4100, then run `npm run dev` in `manifestia-node/frontend`. Vite already proxies `/api` and `/media` to `http://localhost:4100`.

## Deploy on Render

This API is a **Docker** web service on **Python 3.12**. A native Python service defaults to 3.14, cannot install `pydantic-core` (Rust/maturin + read-only Cargo cache), and has no ffmpeg.

1. Push this folder to GitHub. Do **not** commit `.env` or API keys.
2. On an existing failed service: Settings → Runtime = **Docker** (or delete it and create from `render.yaml`). If the git repo is the whole `vision-reel` workspace, set **Root Directory** to `manifestia-python`.
3. Confirm the build uses `python:3.12-slim-bookworm`, not `/opt/render/project/src/.venv/bin/python3.14`.
4. Paste secrets in the dashboard (`BYTEPLUS_API_KEY`, stock keys). Leave `PORT` unset. Disk paths from `render.yaml`:
   - `DATABASE_PATH=/var/data/manifestia.db`
   - `STORAGE_ROOT=/var/data/storage`
5. Persistent disk and an always-on instance (Standard / 1 GB recommended) are required: SQLite and generated MP4s live on disk, and in-process reel jobs die if the instance sleeps.
6. After deploy: `https://<service>.onrender.com/health` and `/api-docs`. `PUBLIC_API_URL` is filled from `RENDER_EXTERNAL_URL` when unset or localhost.

`runtime.txt` (`python-3.12.10`) is only a fallback if someone recreates a native Python service. Docker is the real deploy path.
