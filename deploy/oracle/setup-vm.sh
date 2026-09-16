#!/usr/bin/env bash
# Run on an Oracle Linux / Ubuntu Always Free VM as opc (or ubuntu) with sudo.
# Usage:
#   cd /opt/manifestia && sudo bash deploy/oracle/setup-vm.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/manifestia}"
APP_USER="${SUDO_USER:-opc}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo bash deploy/oracle/setup-vm.sh"
  exit 1
fi

echo "==> Installing system packages (Python, ffmpeg, nginx)"
if command -v dnf >/dev/null 2>&1; then
  dnf -y update
  dnf -y install python3.11 python3.11-pip python3.11-devel gcc ffmpeg nginx git curl
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3.11 python3.11-venv python3-pip build-essential ffmpeg nginx git curl
else
  echo "Unsupported distro. Use Oracle Linux or Ubuntu."
  exit 1
fi

if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  echo "ERROR: ffmpeg/ffprobe not on PATH"
  exit 1
fi

echo "==> App directory: $APP_DIR"
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
cd "$APP_DIR"

if [[ ! -f requirements.txt ]]; then
  echo "ERROR: Copy the repo into $APP_DIR first (requirements.txt missing)."
  exit 1
fi

echo "==> Creating venv + installing Python deps"
if [[ ! -d .venv ]]; then
  python3.11 -m venv .venv || python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Preparing .env"
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
  else
    touch .env
  fi
  PUBLIC_IP="$(curl -sf --max-time 5 http://169.254.169.254/opc/v2/vnics/ \
    -H 'Authorization: Bearer Oracle' 2>/dev/null \
    | grep -oE '"publicIp"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | cut -d'"' -f4 || true)"
  if [[ -z "${PUBLIC_IP:-}" ]]; then
    PUBLIC_IP="$(curl -sf --max-time 5 https://ifconfig.me || hostname -I | awk '{print $1}')"
  fi
  # Portable sed for Linux
  if grep -q '^PUBLIC_API_URL=' .env; then
    sed -i "s|^PUBLIC_API_URL=.*|PUBLIC_API_URL=http://${PUBLIC_IP}|" .env
  else
    echo "PUBLIC_API_URL=http://${PUBLIC_IP}" >> .env
  fi
  if grep -q '^NODE_ENV=' .env; then
    sed -i 's|^NODE_ENV=.*|NODE_ENV=production|' .env
  else
    echo "NODE_ENV=production" >> .env
  fi
  echo "Created .env — edit BYTEPLUS_API_KEY and stock keys before generating AI reels."
fi

mkdir -p storage
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Installing systemd service"
install -m 644 deploy/oracle/manifestia.service /etc/systemd/system/manifestia.service
# Align User= with the account that owns the files
sed -i "s/^User=.*/User=${APP_USER}/" /etc/systemd/system/manifestia.service
sed -i "s/^Group=.*/Group=${APP_USER}/" /etc/systemd/system/manifestia.service
systemctl daemon-reload
systemctl enable manifestia
systemctl restart manifestia

echo "==> Configuring nginx reverse proxy on :80"
install -m 644 deploy/oracle/nginx-manifestia.conf /etc/nginx/conf.d/manifestia.conf
# Disable default site if present (Ubuntu)
if [[ -f /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl enable nginx
systemctl restart nginx

echo ""
echo "=============================================="
echo " Manifestia is running behind nginx on port 80"
echo " Health:  http://<PUBLIC_IP>/health"
echo " Docs:    http://<PUBLIC_IP>/docs"
echo " OpenAPI: http://<PUBLIC_IP>/openapi.json"
echo ""
echo " Next:"
echo "  1. OCI Console → Networking → Security List: ingress TCP 80 (and 443 later)"
echo "  2. Edit /opt/manifestia/.env (BYTEPLUS_API_KEY, PUBLIC_API_URL)"
echo "  3. sudo systemctl restart manifestia"
echo "=============================================="
