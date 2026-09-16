# Deploy Manifestia on Oracle Cloud Always Free

Run this FastAPI backend on a free always-on VM so a mobile app can call HTTPS (or HTTP) APIs.

## What you get

| Item | Value |
|---|---|
| Public API base | `http://<PUBLIC_IP>` (add HTTPS later with a domain + certbot) |
| Health | `GET /health` |
| Swagger | `/docs` |
| OpenAPI | `/openapi.json` |
| Mobile routes | `/api/*` and `/media/*` |

Set `PUBLIC_API_URL` to that base URL so `outputUrl` / `mediaUrl` work on devices.

---

## 1. Create an Always Free VM (console)

1. Sign up: [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/)
2. **Compute → Instances → Create instance**
3. Recommended Always Free shape:
   - **Ampere** `VM.Standard.A1.Flex` — 2–4 OCPU, 12–24 GB RAM (shared across free quota)
   - Or x86 `VM.Standard.E2.1.Micro` if Ampere is unavailable in your region
4. Image: **Oracle Linux 8/9** or **Ubuntu 22.04**
5. Networking: assign a **public IP**
6. Upload/download your **SSH key**
7. Create the instance and note the public IP

### Open the firewall (two places)

**A. OCI Security List** (VCN → Subnet → Security List → Ingress):

| Source | Protocol | Port |
|---|---|---|
| `0.0.0.0/0` | TCP | 22 (SSH) |
| `0.0.0.0/0` | TCP | 80 (API) |
| `0.0.0.0/0` | TCP | 443 (optional HTTPS) |

**B. OS firewall** (after SSH):

```bash
# Oracle Linux (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload

# Ubuntu (ufw)
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 2. Copy the app onto the VM

From your PC (PowerShell), with the repo path and key adjusted:

```powershell
scp -i $env:USERPROFILE\.ssh\oracle.key -r `
  C:\Users\ayush.agarwal\Downloads\manifestia-python-main\manifestia-python-main\* `
  opc@<PUBLIC_IP>:/tmp/manifestia-upload/
```

On the VM:

```bash
sudo mkdir -p /opt/manifestia
sudo rsync -a /tmp/manifestia-upload/ /opt/manifestia/
sudo chown -R opc:opc /opt/manifestia
# Ubuntu images often use user `ubuntu` instead of `opc`
```

Or clone from git if the project is in a remote repo:

```bash
sudo mkdir -p /opt/manifestia
sudo chown opc:opc /opt/manifestia
git clone <YOUR_REPO_URL> /opt/manifestia
```

---

## 3. Run the setup script

```bash
cd /opt/manifestia
chmod +x deploy/oracle/setup-vm.sh
sudo bash deploy/oracle/setup-vm.sh
```

This installs Python, **ffmpeg**, nginx, a venv, systemd unit `manifestia`, and proxies port **80 → 4100**.

---

## 4. Configure secrets

```bash
nano /opt/manifestia/.env
```

Minimum for AI reels:

```env
NODE_ENV=production
PORT=4100
PUBLIC_API_URL=http://<PUBLIC_IP>
DATABASE_PATH=./storage/manifestia.db
STORAGE_ROOT=./storage
BYTEPLUS_API_KEY=your_key_here
```

Optional stock keys: `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `UNSPLASH_ACCESS_KEY`, etc.

Restart:

```bash
sudo systemctl restart manifestia
sudo systemctl status manifestia
curl http://127.0.0.1/health
curl http://<PUBLIC_IP>/health
```

---

## 5. Point the mobile app

Use the public base URL (no trailing slash):

```text
API_BASE_URL = http://<PUBLIC_IP>
```

Examples:

```http
POST http://<PUBLIC_IP>/api/auth/register
POST http://<PUBLIC_IP>/api/onboarding/submit
GET  http://<PUBLIC_IP>/api/library?deviceId=...
GET  http://<PUBLIC_IP>/api/reels/{reelId}
GET  http://<PUBLIC_IP>/media/sessions/.../final.mp4
```

CORS already allows `*`. Auth is device-ID based (`deviceId` / `x-device-id`).

---

## 6. Optional: HTTPS with a domain

1. Point a DNS A record to `<PUBLIC_IP>`
2. On the VM:

```bash
sudo dnf install -y certbot python3-certbot-nginx   # Oracle Linux
# or: sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

3. Set `PUBLIC_API_URL=https://api.yourdomain.com` and restart `manifestia`.

---

## Ops cheatsheet

```bash
sudo systemctl status manifestia
sudo journalctl -u manifestia -f
sudo systemctl restart manifestia
sudo nginx -t && sudo systemctl reload nginx
```

Update code after an `rsync`/`git pull`:

```bash
cd /opt/manifestia
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart manifestia
```

---

## Limits to expect

- Always Free Ampere quota is regional and sometimes “out of capacity” — try another region or Micro shape.
- Disk is limited; clean old reels with `python -m scripts.clean_reels` when needed.
- One uvicorn worker is intentional (SQLite + in-process reel jobs).
