"""Main entry point for TgSaverBot."""

import asyncio
from app.application import app

if __name__ == "__main__":
    try:
        asyncio.run(app.run_polling())
    except (KeyboardInterrupt, SystemExit):
        pass
