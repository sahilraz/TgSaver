import asyncio
import logging
import os
import time
from typing import Any, Callable, Optional, Tuple

from telethon import TelegramClient
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    Message,
    MessageMediaDocument,
    MessageMediaPhoto,
)
from app.config import settings
from app.mtproto.fast_transfer import fast_download_file, fast_upload_file
from app.mtproto.media_optimizer import generate_video_thumbnail, get_video_metadata
from app.storage.temporary_files import check_disk_space, temporary_file_context

logger = logging.getLogger(__name__)


class TransferResult:
    def __init__(
        self,
        success: bool,
        dest_message_id: Optional[int] = None,
        bytes_transferred: int = 0,
        elapsed_seconds: float = 0.0,
        speed_mb_s: float = 0.0,
        error: Optional[str] = None,
    ):
        self.success = success
        self.dest_message_id = dest_message_id
        self.bytes_transferred = bytes_transferred
        self.elapsed_seconds = elapsed_seconds
        self.speed_mb_s = speed_mb_s
        self.error = error


class TransferService:
    @staticmethod
    async def transfer_media(
        client: TelegramClient,
        dest_entity: Any,
        message: Message,
        on_progress: Optional[Callable[[int, int, str, float], Any]] = None,
    ) -> TransferResult:
        """Ultra-fast streaming download and parallel upload transfer engine with FFmpeg integration."""
        raw_text = getattr(message, "message", None) or getattr(message, "raw_text", None) or ""
        entities = list(message.entities) if getattr(message, "entities", None) else None

        if not message.media:
            # Plain text message transfer with intact formatting entities
            try:
                sent = await client.send_message(
                    dest_entity,
                    message=raw_text,
                    formatting_entities=entities,
                    silent=True,
                )
                return TransferResult(
                    success=True,
                    dest_message_id=getattr(sent, "id", None),
                    bytes_transferred=len(raw_text.encode("utf-8")) if raw_text else 0,
                )
            except Exception as e:
                return TransferResult(success=False, error=str(e))

        # 1. Determine media metadata and attributes
        file_size = 0
        file_name = "media_file"
        is_video = False
        orig_video_attr: Optional[DocumentAttributeVideo] = None

        if isinstance(message.media, MessageMediaDocument) and message.media.document:
            doc = message.media.document
            file_size = doc.size
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    file_name = attr.file_name
                elif isinstance(attr, DocumentAttributeVideo):
                    is_video = True
                    orig_video_attr = attr
        elif isinstance(message.media, MessageMediaPhoto):
            file_name = "photo.jpg"
            file_size = getattr(message.media.photo, "size", 1024 * 1024) if hasattr(message.media, "photo") else 1024 * 1024

        # Check video by extension if not flagged yet
        ext = os.path.splitext(file_name)[1].lower()
        if ext in (".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"):
            is_video = True

        # Pre-check disk space
        if file_size > 0 and not check_disk_space(required_bytes=file_size):
            return TransferResult(
                success=False,
                error="Insufficient host disk space to download this file.",
            )

        start_time = time.monotonic()
        total_bytes = 0

        async with temporary_file_context(suffix=f"_{file_name}") as temp_file:
            download_path = str(temp_file)
            last_edit = 0.0

            def download_progress(received_bytes: int, total: int):
                nonlocal last_edit
                now = time.monotonic()
                if on_progress and (now - last_edit >= settings.PROGRESS_UPDATE_INTERVAL or received_bytes >= total):
                    last_edit = now
                    elapsed = max(0.1, now - start_time)
                    speed = (received_bytes / (1024 * 1024)) / elapsed
                    asyncio.create_task(on_progress(received_bytes, total, "DOWNLOADING", speed))

            # 2. Fast Parallel Download Phase
            download_success = False
            if isinstance(message.media, MessageMediaDocument) and message.media.document and file_size > 0:
                try:
                    logger.info(f"Downloading {file_name} ({file_size / (1024*1024):.1f} MB) with parallel engine...")
                    await fast_download_file(
                        client,
                        message.media.document,
                        download_path,
                        file_size,
                        progress_callback=download_progress,
                    )
                    download_success = os.path.exists(download_path) and os.path.getsize(download_path) > 0
                except Exception as e:
                    logger.warning(f"Parallel download encountered exception ({e}); falling back to standard chunked download.")
                    download_success = False

            if not download_success:
                try:
                    downloaded = await client.download_media(
                        message,
                        file=download_path,
                        progress_callback=download_progress,
                    )
                    download_success = bool(downloaded and os.path.exists(download_path))
                except Exception as e:
                    logger.error(f"Download failed for message {message.id}: {e}")
                    return TransferResult(success=False, error=f"Download failure: {str(e)}")

            if not download_success or not os.path.exists(download_path):
                return TransferResult(success=False, error="Failed to download media to temporary storage.")

            total_bytes = os.path.getsize(download_path)

            # 3. Video optimization & FFmpeg thumbnail extraction if applicable
            thumb_path = None
            upload_attributes = []
            if isinstance(message.media, MessageMediaDocument) and message.media.document:
                upload_attributes = list(message.media.document.attributes)

            if is_video:
                w, h, duration = await get_video_metadata(download_path)
                if not w and orig_video_attr:
                    w = orig_video_attr.w
                    h = orig_video_attr.h
                    duration = orig_video_attr.duration

                # Generate video thumbnail if ffmpeg is available
                thumb_target = f"{download_path}_thumb.jpg"
                thumb_path = await generate_video_thumbnail(download_path, thumb_target)

                # Ensure DocumentAttributeVideo is configured for streaming
                if w and h and duration:
                    upload_attributes = [
                        a for a in upload_attributes if not isinstance(a, DocumentAttributeVideo)
                    ]
                    upload_attributes.append(
                        DocumentAttributeVideo(
                            duration=int(duration),
                            w=int(w),
                            h=int(h),
                            supports_streaming=True,
                        )
                    )

            # 4. Fast Parallel Upload Phase
            upload_start = time.monotonic()
            last_upload_edit = 0.0

            def upload_progress(sent_bytes: int, total: int):
                nonlocal last_upload_edit
                now = time.monotonic()
                if on_progress and (now - last_upload_edit >= settings.PROGRESS_UPDATE_INTERVAL or sent_bytes >= total):
                    last_upload_edit = now
                    elapsed = max(0.1, now - upload_start)
                    speed = (sent_bytes / (1024 * 1024)) / elapsed
                    asyncio.create_task(on_progress(sent_bytes, total, "UPLOADING", speed))

            has_spoiler = bool(getattr(message.media, "spoiler", False))

            try:
                # Try parallel 512KB upload first
                uploaded_input_file = None
                try:
                    logger.info(f"Uploading {file_name} ({total_bytes / (1024*1024):.1f} MB) with parallel engine...")
                    uploaded_input_file = await fast_upload_file(
                        client,
                        download_path,
                        progress_callback=upload_progress,
                    )
                except Exception as e:
                    logger.warning(f"Parallel upload encountered exception ({e}); falling back to standard send_file.")
                    uploaded_input_file = None

                target_file_to_send = uploaded_input_file or download_path

                # Wrap with spoiler container if original media had a spoiler
                if has_spoiler:
                    from telethon.tl.types import InputMediaUploadedPhoto, InputMediaUploadedDocument
                    if not uploaded_input_file:
                        uploaded_input_file = await client.upload_file(
                            download_path, file_size=total_bytes, progress_callback=upload_progress
                        )

                    is_photo = isinstance(message.media, MessageMediaPhoto) or (ext in (".jpg", ".jpeg", ".png", ".webp"))
                    if is_photo:
                        target_file_to_send = InputMediaUploadedPhoto(
                            file=uploaded_input_file,
                            spoiler=True,
                        )
                    else:
                        uploaded_thumb = None
                        if thumb_path and os.path.exists(thumb_path):
                            uploaded_thumb = await client.upload_file(thumb_path)
                        mime = getattr(getattr(message.media, "document", None), "mime_type", None) or "video/mp4" if is_video else "application/octet-stream"
                        target_file_to_send = InputMediaUploadedDocument(
                            file=uploaded_input_file,
                            mime_type=mime,
                            attributes=upload_attributes,
                            thumb=uploaded_thumb,
                            spoiler=True,
                            force_file=not is_video and not is_photo,
                        )

                sent = await client.send_file(
                    dest_entity,
                    file=target_file_to_send,
                    caption=raw_text,
                    formatting_entities=entities,
                    attributes=upload_attributes if (upload_attributes and not hasattr(target_file_to_send, "spoiler")) else None,
                    thumb=thumb_path if not hasattr(target_file_to_send, "spoiler") else None,
                    progress_callback=upload_progress if (uploaded_input_file is None and not hasattr(target_file_to_send, "spoiler")) else None,
                    silent=True,
                )

                total_elapsed = max(0.1, time.monotonic() - start_time)
                avg_speed = (total_bytes / (1024 * 1024)) / total_elapsed
                dest_id = sent[0].id if isinstance(sent, list) and sent else getattr(sent, "id", None)

                return TransferResult(
                    success=True,
                    dest_message_id=dest_id,
                    bytes_transferred=total_bytes,
                    elapsed_seconds=total_elapsed,
                    speed_mb_s=round(avg_speed, 2),
                )
            except Exception as e:
                logger.error(f"Upload failed for message {message.id}: {e}")
                return TransferResult(success=False, error=f"Upload failure: {str(e)}")
            finally:
                if thumb_path and os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except Exception:
                        pass
