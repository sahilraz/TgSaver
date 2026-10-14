# 🚀 Complete Deployment Guide — TgSaverBot

This guide provides end-to-end instructions for deploying TgSaverBot across all supported platforms:
- **[1. Antideploy](#1-deploying-on-antideploy)**
- **[2. Render](#2-deploying-on-render)**
- **[3. Vercel](#3-deploying-on-vercel)**
- **[4. Heroku](#4-deploying-on-heroku)**
- **[5. Ubuntu VPS](#5-deploying-on-ubuntu-vps)**

---

## 🔑 Required Credentials

Before deploying to any platform, prepare your core Telegram credentials:
1. **Telegram API ID & API Hash:**
   - Go to [https://my.telegram.org](https://my.telegram.org)
   - Log in and navigate to **API Development tools**
   - Create an application to get your `API_ID` (numeric) and `API_HASH` (string)
2. **Telegram Bot Token:**
   - Open [@BotFather](https://t.me/BotFather) in Telegram
   - Run `/newbot` and follow prompts to obtain your `BOT_TOKEN`
3. **Encryption Key:**
   - Generate a 32-byte Fernet key:
     ```bash
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```

---

## 1. Deploying on Antideploy

Antideploy provides instant zero-configuration deployment with managed PostgreSQL and automated container execution.

### Step 1: Connect your Account
1. Open the approval prompt:
   - Go to [https://antideploy.com/activate](https://antideploy.com/activate)
   - Or upload your repository directly in the web console at [https://antideploy.com/console](https://antideploy.com/console).

### Step 2: Configure Environment Variables
In the Antideploy application settings, set:
- `API_ID`: Your Telegram API ID
- `API_HASH`: Your Telegram API Hash
- `BOT_TOKEN`: Your Telegram Bot Token
- `ENCRYPTION_KEY`: Your generated 32-byte Fernet key

*Note: Antideploy automatically provisions and injects `DATABASE_URL` into your running container.*

### Step 3: Start Application
Antideploy automatically detects the repository's `Procfile` / `Dockerfile`:
- The application boots `uvicorn api.webhook_handler:web_app` for webhooks or `python main.py` for polling mode.
- Your application will be live at `https://<your-subdomain>.antideploy.app`.

---

## 2. Deploying on Render

Render supports a combined Web Service, Background Worker, Managed PostgreSQL, and Redis instance using the included `render.yaml` Blueprint.

### Step 1: Fork or Push Repository
Push this repository to your GitHub or GitLab account.

### Step 2: Create a Blueprint Instance
1. Go to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** ➔ **Blueprint**.
3. Select your repository. Render will automatically parse `render.yaml` and configure:
   - **`tgsaver-web`**: Webhook API & health check service
   - **`tgsaver-worker`**: MTProto transfer worker
   - **`tgsaver-db`**: Managed PostgreSQL database
   - **`tgsaver-redis`**: Managed Redis queue

### Step 3: Set Secrets
Provide the required environment variables in Render:
- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `ENCRYPTION_KEY`

Click **Apply** to deploy all services.

---

## 3. Deploying on Vercel

Vercel hosts the lightweight, instant-response serverless webhook interface.

### Step 1: Deploy Project
Install Vercel CLI and deploy:
```bash
vercel
```

### Step 2: Configure Environment Variables
In your Vercel Project Settings (Settings ➔ Environment Variables), set:
- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `DATABASE_URL`: Connection string to an external PostgreSQL database (e.g. Neon, Supabase, or Render Postgres)
- `ENCRYPTION_KEY`: Fernet master key
- `REDIS_URL`: Connection string to Upstash Redis or Render Redis
- `WEBHOOK_URL`: `https://<your-vercel-app>.vercel.app/webhook`
- `WEBHOOK_SECRET`: A secret string of your choice

### Step 3: Register Telegram Webhook
Run the following curl command once:
```bash
curl -F "url=https://<your-vercel-app>.vercel.app/webhook" \
     -F "secret_token=<YOUR_WEBHOOK_SECRET>" \
     "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook"
```

*Note: Serverless functions on Vercel handle command responses, dashboards, and job queuing. To execute heavy MTProto file transfers, run a persistent background worker on Render or Ubuntu VPS connected to the same database/Redis queue.*

---

## 4. Deploying on Heroku

Heroku runs the bot web and background worker dynos using the included `Procfile`.

### Step 1: Create Heroku App
```bash
heroku create tgsaver-bot
```

### Step 2: Add Database & Redis Add-ons
```bash
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini
```

### Step 3: Set Configuration Variables
```bash
heroku config:set API_ID="12345678"
heroku config:set API_HASH="your_api_hash"
heroku config:set BOT_TOKEN="your_bot_token"
heroku config:set ENCRYPTION_KEY="your_fernet_key"
```

### Step 4: Deploy & Scale Dynos
```bash
git push heroku main
heroku ps:scale web=1 worker=1
```

---

## 5. Deploying on Ubuntu VPS (22.04 / 24.04 LTS)

Ubuntu VPS deployment provides the highest practical MTProto throughput with low network latency and direct local file streaming.

### Step 1: Run Automated Setup Script
```bash
git clone https://github.com/your-username/TgSaverBot.git /opt/tgsaver
cd /opt/tgsaver
chmod +x scripts/install_ubuntu.sh
sudo ./scripts/install_ubuntu.sh
```

### Step 2: Configure `.env`
Edit `/opt/tgsaver/.env` with your credentials:
```bash
sudo nano /opt/tgsaver/.env
```

```env
API_ID=12345678
API_HASH=abcdef0123456789abcdef0123456789
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
DATABASE_URL=postgresql+asyncpg://tgsaver:password@localhost:5432/tgsaver
ENCRYPTION_KEY=your_generated_fernet_key
```

### Step 3: Start Systemd Services
```bash
sudo systemctl enable --now tgsaver-bot
sudo systemctl enable --now tgsaver-worker
```

### Step 4: Monitor Logs & Status
```bash
sudo systemctl status tgsaver-bot
sudo systemctl status tgsaver-worker

# Realtime logs
journalctl -u tgsaver-bot -f
journalctl -u tgsaver-worker -f
```

---

## 🔍 Verification & Health Check

Once your deployment is live:
1. Open your bot in Telegram and send `/start`.
2. Send `/ping` to check response latency:
   ```text
   🏓 Pong!  ·  48ms
   ```
3. Send `/health` to verify database status, CPU, RAM, and free disk space.
4. Click **Connect Telegram Account** to link your account and begin saving posts.
