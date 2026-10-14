"""Health check diagnostics separating liveness and readiness probes."""

import logging
from typing import Dict, Any
import psutil
from sqlalchemy import text
from app.config import settings
from app.database.session import get_db_session
from app.storage.temporary_files import get_disk_free_gb

logger = logging.getLogger(__name__)


class HealthCheckService:
    @staticmethod
    async def check_liveness() -> Dict[str, Any]:
        """Simple liveness probe confirming process is responsive."""
        return {
            "status": "alive",
            "profile": settings.effective_profile.value,
        }

    @staticmethod
    async def check_readiness() -> Dict[str, Any]:
        """Deep readiness probe checking database, queue, host resources."""
        db_ok = False
        db_error = None
        try:
            async with get_db_session() as session:
                await session.execute(text("SELECT 1"))
                db_ok = True
        except Exception as e:
            db_error = str(e)

        # Host system resources
        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk_free = get_disk_free_gb()

        all_ok = db_ok and (disk_free >= 0.5)

        return {
            "status": "ready" if all_ok else "degraded",
            "database": {"ok": db_ok, "error": db_error},
            "host_resources": {
                "cpu_percent": cpu_pct,
                "memory_used_percent": mem.percent,
                "disk_free_gb": round(disk_free, 2),
            },
            "profile": settings.effective_profile.value,
        }


health_service = HealthCheckService()
