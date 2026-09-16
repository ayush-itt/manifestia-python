# Deploy Manifestia on Render (Free)

Public HTTPS API for the mobile app. No credit card required for Free web services.

## Limits (Free)

| Behavior | Effect |
|---|---|
| Sleep after **15 min** idle | First request after sleep ~**1 min** cold start |
| Ephemeral disk | SQLite + `/media` MP4s **wiped** on sleep / redeploy / restart |
| 512 MB RAM / 0.1 CPU | Heavy AI + ffmpeg jobs may be slow or OOM |
| URL stays the same | `https://<service>.onrender.com` never changes on sleep |

Good for demos and mobile API integration. Not ideal as permanent production storage for reels.

---

## 1. Put the project on GitHub

Render deploys from Git. From the project folder:

```powershell
cd C:\Users\ayush.agarwal\Downloads\manifestia-python-main\manifestia-python-main
git init
git add .
git commit -m "Add Render Docker deploy for Manifestia API"
```

Create a **private** GitHub repo, then:

```powershell
gh repo create manifestia-python --private --source=. --remote=origin --push
```

Or create the repo in the GitHub UI and:

```powershell
git remote add origin https://github.com/<YOU>/manifestia-python.git
git branch -M main
git push -u origin main
```

Do **not** commit `.env` (secrets go in the Render dashboard).

---

## 2. Create the Render service

### Option A — Blueprint (uses `render.yaml`)

1. Sign up at [render.com](https://render.com) (GitHub login is fine)
2. **New → Blueprint**
3. Connect the GitHub repo
4. Apply the Blueprint → plan **Free**
5. When prompted, set secrets:
   - `PUBLIC_API_URL` → leave blank until first deploy finishes, then set to `https://<service>.onrender.com`
   - `BYTEPLUS_API_KEY` → your key (needed for AI reels)
   - optional stock keys

### Option B — Manual Web Service

1. **New → Web Service**
2. Connect the repo
3. Runtime: **Docker**
4. Instance type: **Free**
5. Health check path: `/health`
6. Add the same env vars as in `render.yaml`

First build can take several minutes (`content/` is ~172 MB + ffmpeg).

---

## 3. After deploy — set public URL

In **Dashboard → your service → Environment**:

```text
PUBLIC_API_URL=https://manifestia-api-xxxx.onrender.com
```

(Use your real `.onrender.com` hostname — no trailing slash.)

Save → service redeploys. Then:

```text
https://<your-service>.onrender.com/health
https://<your-service>.onrender.com/docs
```

---

## 4. Mobile app base URL

```text
API_BASE_URL = https://<your-service>.onrender.com
```

Examples:

```http
GET  /health
POST /api/auth/register
POST /api/onboarding/submit
GET  /api/library?deviceId=...
GET  /api/reels/{reelId}
GET  /media/...
```

**Tip:** On the first call after sleep, wait ~60s or retry once so cold start doesn’t look like an app bug.

---

## 5. Local Docker smoke test (optional)

```powershell
cd C:\Users\ayush.agarwal\Downloads\manifestia-python-main\manifestia-python-main
docker build -t manifestia-api .
docker run --rm -p 4100:4100 -e PUBLIC_API_URL=http://localhost:4100 -e BYTEPLUS_API_KEY= manifestia-api
```

Open http://localhost:4100/health

---

## Ops

- Logs: Render Dashboard → service → **Logs**
- Redeploy: push to `main`, or **Manual Deploy**
- Wipe expectation: after every sleep, treat DB/media as empty unless you move storage later (e.g. paid disk / object storage)
