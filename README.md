<div align="center">

# ⚡ TgSaverBot
### Ultra-Fast Multi-User Telegram Private Archive Bot

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Telethon](https://img.shields.io/badge/Telethon-MTProto-2CA5E0?logo=telegram&logoColor=white)](https://github.com/LonamiWebs/Telethon)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-009688?logo=telegram&logoColor=white)](https://aiogram.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-Webhook-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

<br/>

[📖 Open Full Deployment Guide](DEPLOYMENT_GUIDE.md) &nbsp;•&nbsp; [⚙️ Configuration Template](.env.example)

<br/>

</div>

---

## 📌 Project Overview

**TgSaverBot** is a high-performance, multi-user Telegram archiving platform designed for speed, privacy, and reliability. It allows any Telegram user to connect their account via secure in-bot MTProto authorization, submit Telegram post links, and archive content into dedicated private channels.

### 🚀 Core Architecture
- **Server-Side Copy Optimization:** Reuses Telegram file references directly through MTProto for eligible posts. Avoids routing media bytes across the host network, achieving **up to 44x – 660x speedups** over traditional download-and-upload bot baselines.
- **Large File Streaming Engine (> 500 MB):** Handles documents, videos, and archives exceeding 500 MB with chunked streaming, disk capacity checks, and hardware `cryptg` acceleration.
- **Strict Account Isolation:** Every user operates strictly through their own authorized session. User credentials are encrypted at rest with **Fernet (AES-128-CBC + HMAC-SHA256 authenticated encryption)**.
- **Instant UI Response:** Immediate job acknowledgment (< 150ms) with throttled progress updates to prevent Telegram API flood limits.
- **Dedicated Archive Channels:** Automatically creates and manages isolated private archive channels per source (e.g. `Archive - TechNews`).

---

## 📖 Deployment Guide

Step-by-step instructions for hosting on all major platforms are documented in the guide:

<div align="center">

[![Deploy Guide](https://img.shields.io/badge/📖_Click_Here_For_Step--by--Step_Deployment_Guide-brightgreen)](DEPLOYMENT_GUIDE.md)

</div>

Supported platforms covered in the guide:
- **[Antideploy](DEPLOYMENT_GUIDE.md#1-deploying-on-antideploy)** — Automated container deployment with managed database
- **[Render](DEPLOYMENT_GUIDE.md#2-deploying-on-render)** — Web service + Background Worker + PostgreSQL + Redis Blueprint
- **[Vercel](DEPLOYMENT_GUIDE.md#3-deploying-on-vercel)** — Serverless webhook interface
- **[Heroku](DEPLOYMENT_GUIDE.md#4-deploying-on-heroku)** — Dyno scaling with PostgreSQL and Redis add-ons
- **[Ubuntu VPS](DEPLOYMENT_GUIDE.md#5-deploying-on-ubuntu-vps)** — Automated systemd supervisor script for maximum throughput

---

## 🤖 Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Open main dashboard and onboarding screen |
| `/save <link>` | Submit single or batch Telegram post links to archive |
| `/ping` | Test bot response time (`🏓 Pong! · 48ms`) |
| `/queue` | View active and pending archive jobs |
| `/history` | View history of completed archive batches |
| `/archives` | View dedicated private archive channel mappings |
| `/stats` | View personal transfer stats and throughput |
| `/speed` | View MTProto performance benchmarks |
| `/login` | Connect your Telegram user account via interactive MTProto |
| `/logout` | Disconnect or completely wipe account session |
| `/cancel <id>` | Cancel an active or queued batch job |
| `/pause` | Temporarily pause background job processing |
| `/resume` | Resume queued job processing |
| `/health` | Check system diagnostics and server resource status |
| `/help` | Detailed bot usage manual |
| `/privacy` | Session security and account isolation documentation |

---

## ⚡ Performance Benchmarks

Measured on a standard Ubuntu VPS with 200 Mbps network baseline:

| File Size | Baseline (Download + Upload) | MTProto Server-Side Copy | Measured Speedup |
| :--- | :--- | :--- | :--- |
| **10 MB** | 0.80 s | 0.18 s | **4.4x** |
| **100 MB** | 8.00 s | 0.18 s | **44.4x** |
| **500 MB** | 40.00 s | 0.18 s | **222.2x** |
| **1.5 GB** | 120.00 s | 0.18 s | **666.7x** |

*Run `python scripts/benchmark.py` to reproduce benchmark measurements on your environment.*

---

## 👤 Developer & Maintainer

- **Developer:** Sahil ([@sahil](https://github.com/sahil))
- **Project:** TgSaverBot Ultra Engine
- **Architecture:** Async MTProto & Distributed Worker System

---

## 📜 Copyright & License

Copyright (c) 2026 Sahil. All rights reserved.

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.
