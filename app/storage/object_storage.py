"""Object storage abstraction for deployments requiring external storage."""

from typing import Optional
from pathlib import Path


class ObjectStorageService:
    """Provides a pluggable interface for S3 / Cloudflare R2 / GCS when needed."""

    def __init__(self, endpoint: Optional[str] = None, bucket: Optional[str] = None):
        self.endpoint = endpoint
        self.bucket = bucket

    async def upload_file(self, local_path: Path, remote_key: str) -> Optional[str]:
        # Pluggable backend for external persistent blob storage
        return None

    async def download_file(self, remote_key: str, local_path: Path) -> bool:
        return False
