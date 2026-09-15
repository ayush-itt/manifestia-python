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

- Backend: Python 3.11+ + FastAPI + SQLite + OpenAPI
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
