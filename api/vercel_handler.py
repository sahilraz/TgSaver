"""Vercel Serverless Function entry point.

Handles webhooks and UI commands within short-lived serverless invocations.
"""

from api.webhook_handler import web_app

# Vercel ASGI application export
app = web_app
