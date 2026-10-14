"""Default Vercel index entry point."""

from api.webhook_handler import web_app

app = web_app
