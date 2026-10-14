import asyncio
import json
import logging
import os
import shutil
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def is_ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


async def get_video_metadata(video_path: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Extracts (width, height, duration) using ffprobe if available on system."""
    if not is_ffprobe_available() or not os.path.exists(video_path):
        return None, None, None

    try:
        proc = await asyncio.create_subprocess_exec(
            shutil.which("ffprobe"),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration:format=duration",
            "-of", "json",
            video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8.0)
        data = json.loads(stdout.decode())
        streams = data.get("streams", [])
        format_data = data.get("format", {})

        w, h, dur = None, None, None
        if streams:
            w = streams[0].get("width")
            h = streams[0].get("height")
            dur = streams[0].get("duration")

        if not dur and "duration" in format_data:
            dur = format_data["duration"]

        duration_int = int(float(dur)) if dur else None
        return w, h, duration_int
    except Exception as e:
        logger.debug(f"FFprobe extraction skipped: {e}")
        return None, None, None


async def generate_video_thumbnail(video_path: str, thumb_output_path: str) -> Optional[str]:
    """Generates a high-quality video thumbnail using ffmpeg if available."""
    if not is_ffmpeg_available() or not os.path.exists(video_path):
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-loglevel", "error",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            "-vf", "scale='min(320,iw)':-1",
            "-q:v", "2",
            "-y",
            thumb_output_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10.0)
        if os.path.exists(thumb_output_path) and os.path.getsize(thumb_output_path) > 0:
            return thumb_output_path
    except Exception as e:
        logger.debug(f"Thumbnail generation skipped: {e}")

    return None
