"""Message retrieval, album grouping detection, and metadata extraction."""

import logging
from typing import List, Optional, Tuple, Any
from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaDocument, MessageMediaPhoto

logger = logging.getLogger(__name__)


class MessageMetadata:
    def __init__(
        self,
        has_media: bool,
        media_type: str,
        file_name: Optional[str],
        file_size: Optional[int],
        caption: Optional[str],
        grouped_id: Optional[int],
        noforwards: bool,
    ):
        self.has_media = has_media
        self.media_type = media_type
        self.file_name = file_name
        self.file_size = file_size
        self.caption = caption
        self.grouped_id = grouped_id
        self.noforwards = noforwards


class MessageService:
    @staticmethod
    async def get_message(client: TelegramClient, entity: Any, message_id: int) -> Optional[Message]:
        """Fetches a single message from the specified entity."""
        try:
            return await client.get_messages(entity, ids=message_id)
        except Exception as e:
            logger.error(f"Failed to fetch message {message_id}: {e}")
            return None

    @staticmethod
    async def get_album_messages(client: TelegramClient, entity: Any, message: Message) -> List[Message]:
        """If message is part of an album (grouped_id), retrieves all messages belonging to the album."""
        if not getattr(message, "grouped_id", None):
            return [message]

        grouped_id = message.grouped_id
        # Scan messages around the target message id to collect the album
        start_id = max(1, message.id - 10)
        end_id = message.id + 10
        try:
            messages = await client.get_messages(entity, min_id=start_id, max_id=end_id)
            album = [m for m in messages if getattr(m, "grouped_id", None) == grouped_id]
            # Ensure target message is included
            if not any(m.id == message.id for m in album):
                album.append(message)
            # Sort by ID ascending to preserve correct ordering
            album.sort(key=lambda m: m.id)
            return album
        except Exception as e:
            logger.warning(f"Error fetching album messages for grouped_id {grouped_id}: {e}")
            return [message]

    @staticmethod
    def extract_metadata(message: Message) -> MessageMetadata:
        """Extracts detailed metadata, file size, name, and restriction status."""
        has_media = bool(message.media)
        media_type = "text"
        file_name = None
        file_size = None
        noforwards = bool(getattr(message, "noforwards", False))

        if message.media:
            if isinstance(message.media, MessageMediaPhoto):
                media_type = "photo"
            elif isinstance(message.media, MessageMediaDocument):
                doc = message.media.document
                if doc:
                    file_size = doc.size
                    media_type = "document"
                    for attr in doc.attributes:
                        if hasattr(attr, "file_name"):
                            file_name = attr.file_name
                        elif hasattr(attr, "duration"):
                            media_type = "video"
            else:
                media_type = "media"

        return MessageMetadata(
            has_media=has_media,
            media_type=media_type,
            file_name=file_name,
            file_size=file_size,
            caption=message.text,
            grouped_id=getattr(message, "grouped_id", None),
            noforwards=noforwards,
        )
