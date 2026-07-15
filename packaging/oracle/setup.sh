#!/usr/bin/env bash
# Garmin Coach — installer for an Oracle Cloud "Always Free" Ubuntu ARM VM.
# Run it on the VM as the default 'ubuntu' user:
#     bash setup.sh
# It installs Python 3.13, the app, the Claude CLI, Tailscale, and wires the app
# + a nightly sync as systemd services. Interactive logins come after (printed).
set -euo pipefail

REPO="${REPO:-https://github.com/omri566/garmin-coach.git}"
APP_DIR="${APP_DIR:-$HOME/garmin-coach}"
PY=python3.13
USER_NAME="$(whoami)"

echo "== 1/6  system packages =="
sudo apt-get update -y
sudo apt-get install -y software-properties-common curl git build-essential
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update -y
sudo apt-get install -y "$PY" "${PY}-venv" "${PY}-dev"

echo "== 2/6  clone + venv + deps =="
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO" "$APP_DIR"        # private repo? clone once yourself with a PAT first
fi
cd "$APP_DIR"
"$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "== 3/6  Claude CLI (your subscription powers the AI) =="
command -v claude >/dev/null 2>&1 || curl -fsSL https://claude.ai/install.sh | bash

echo "== 4/6  Tailscale (private phone access) =="
command -v tailscale >/dev/null 2>&1 || curl -fsSL https://tailscale.com/install.sh | sh

echo "== 5/6  systemd: app service + nightly sync timer =="
BIN="$APP_DIR/.venv/bin/python"
GUNICORN="$APP_DIR/.venv/bin/gunicorn"
ENVPATH="$HOME/.local/bin:$HOME/.claude/local:/usr/local/bin:/usr/bin:/bin"

sudo tee /etc/systemd/system/garmin-coach.service >/dev/null <<UNIT
[Unit]
Description=Garmin Coach dashboard
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$APP_DIR
Environment=GC_HOST=0.0.0.0
Environment=GC_PORT=8050
Environment=GC_DEBUG=0
Environment=GC_DATA_DIR=$APP_DIR/data
Environment=PATH=$ENVPATH
# Production WSGI server (not the Flask dev server). One worker keeps the app's
# in-process caches coherent; gthread lets slow LLM calls (coach tips) run without
# blocking other requests. --timeout 180 so a long LLM call isn't killed.
ExecStart=$GUNICORN --workers 1 --threads 8 --worker-class gthread --timeout 180 --bind 0.0.0.0:8050 garmin_coach.dashboard.app:server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo tee /etc/systemd/system/garmin-coach-sync.service >/dev/null <<UNIT
[Unit]
Description=Garmin Coach nightly sync (activities + health + recommendations)
After=network-online.target

[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=$APP_DIR
Environment=GC_DATA_DIR=$APP_DIR/data
Environment=PATH=$ENVPATH
ExecStart=$BIN -m garmin_coach.pipeline
UNIT

sudo tee /etc/systemd/system/garmin-coach-sync.timer >/dev/null <<UNIT
[Unit]
Description=Run Garmin Coach sync daily

[Timer]
OnCalendar=*-*-* 05:30:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload

echo
echo "== 6/6  done — now the interactive steps (run these yourself) =="
cat <<STEPS

  1) Tailscale:   sudo tailscale up
                  (open the printed URL, sign in; install Tailscale on your phone, same login)

  2) Claude:      claude auth login          # sign in with your Claude subscription
                  # if that can't open a browser, use:  claude setup-token

  3) Garmin:      cd $APP_DIR && GC_DATA_DIR=$APP_DIR/data \\
                     .venv/bin/python -m garmin_coach.ingest.sync --limit 1
                  (type your Garmin email/password + the MFA code once)

  4) (optional) seed with your Mac's history instead of a fresh sync:
                  # run this ON YOUR MAC:
                  scp -r ~/programming/garmin-coach/data ubuntu@<VM_PUBLIC_IP>:$APP_DIR/

  5) First full sync + start everything:
                  GC_DATA_DIR=$APP_DIR/data .venv/bin/python -m garmin_coach.pipeline
                  sudo systemctl enable --now garmin-coach.service garmin-coach-sync.timer

  6) Your phone URL (Tailscale on):
                  echo "http://\$(tailscale ip -4):8050"

STEPS
