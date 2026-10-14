"""Temporary file management with disk space checking and safe cleanup."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
import shutil
import uuid
from typing import AsyncGenerator, Optional
import aiofiles.os
import psutil
from app.config import settings


def get_disk_free_gb(path: Optional[str] = None) -> float:
    """Returns free disk space in Gigabytes for the target directory drive."""
    target_path = path or str(settings.temp_path)
    try:
        usage = psutil.disk_usage(target_path)
        return usage.free / (1024 ** 3)
    except Exception:
        # Fallback to root or 5.0 GB if check fails
        return 5.0


def check_disk_space(required_bytes: int = 0) -> bool:
    """Checks whether there is enough disk space including buffer."""
    free_gb = get_disk_free_gb()
    required_gb = (required_bytes / (1024 ** 3)) + settings.MIN_DISK_FREE_GB
    return free_gb >= required_gb


@asynccontextmanager
async def temporary_file_context(suffix: str = "") -> AsyncGenerator[Path, None]:
    """Yields a unique temporary file path and guarantees deletion on exit."""
    temp_dir = settings.temp_path
    unique_id = uuid.uuid4().hex
    temp_file = temp_dir / f"tg_dl_{unique_id}{suffix}"

    try:
        yield temp_file
    finally:
        try:
            if temp_file.exists():
                await aiofiles.os.remove(temp_file)
        except Exception:
            pass


def cleanup_all_temp_files() -> int:
    """Cleans up leftover files in the temporary downloads directory."""
    temp_dir = settings.temp_path
    count = 0
    if temp_dir.exists():
        for file in temp_dir.glob("tg_dl_*"):
            try:
                if file.is_file():
                    file.unlink(missing_ok=True)
                    count += 1
            except Exception:
                pass
    return count
