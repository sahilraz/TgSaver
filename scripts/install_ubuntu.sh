#!/usr/bin/env bash
# ==============================================================================
# TgSaverBot Ubuntu VPS Automated Installation Script
# ==============================================================================
set -euo pipefail

echo ">>> [1/6] Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    build-essential \
    libffi-dev \
    libssl-dev \
    postgresql \
    postgresql-contrib \
    redis-server \
    curl \
    git \
    ufw

echo ">>> [2/6] Creating service user 'tgsaver'..."
if ! id "tgsaver" &>/dev/null; then
    sudo useradd -m -s /bin/bash tgsaver
fi

APP_DIR="/opt/tgsaver"
sudo mkdir -p "$APP_DIR"
sudo chown -R tgsaver:tgsaver "$APP_DIR"

echo ">>> [3/6] Setting up Python virtual environment..."
sudo -u tgsaver python3 -m venv "$APP_DIR/.venv"
sudo -u tgsaver "$APP_DIR/.venv/bin/pip" install --upgrade pip
if [ -f "requirements.txt" ]; then
    sudo cp -r . "$APP_DIR/"
    sudo chown -R tgsaver:tgsaver "$APP_DIR"
    sudo -u tgsaver "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
fi

echo ">>> [4/6] Configuring Systemd services..."
sudo cp "$APP_DIR/systemd/tgsaver-bot.service" /etc/systemd/system/
sudo cp "$APP_DIR/systemd/tgsaver-worker.service" /etc/systemd/system/
sudo systemctl daemon-reload

echo ">>> [5/6] Checking Postgres and Redis..."
sudo systemctl enable --now postgresql
sudo systemctl enable --now redis-server

echo ">>> [6/6] Installation Complete!"
echo "Please edit $APP_DIR/.env with your API credentials and run:"
echo "sudo systemctl enable --now tgsaver-bot"
echo "sudo systemctl enable --now tgsaver-worker"
