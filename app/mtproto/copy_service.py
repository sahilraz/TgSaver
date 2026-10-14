"""Ultra-fast MTProto server-side copy optimization without routing media bytes."""

import logging
from typing import List, Optional, Tuple, Any
from telethon import TelegramClient
from telethon.errors import (
    ChatForwardsRestrictedError,
    ChatWriteForbiddenError,
    RPCError,
)
from telethon.tl.types import Message

logger = logging.getLogger(__name__)


class CopyResult:
    def __init__(
        self,
        success: bool,
        dest_message_id: Optional[int] = None,
        is_protected: bool = False,
        error: Optional[str] = None,
    ):
        self.success = success
        self.dest_message_id = dest_message_id
        self.is_protected = is_protected
        self.error = error


class CopyService:
    @staticmethod
    async def copy_message(
        client: TelegramClient,
        dest_entity: Any,
        message: Message,
    ) -> CopyResult:
        """Copies message server-side directly through MTProto without downloading bytes."""
        # 1. Respect Telegram Content Protection
        if getattr(message, "noforwards", False):
            return CopyResult(
                success=False,
                is_protected=True,
                error="Content protection is enabled on this post. Telegram prohibits copying.",
            )

        try:
            # Preserve raw message text and exact entities to preserve formatting (bold, italic, links, spoilers, etc.)
            raw_text = getattr(message, "message", None) or getattr(message, "raw_text", None) or ""
            entities = list(message.entities) if getattr(message, "entities", None) else None

            # For messages with media, use send_file with message.media to reuse file reference on MTProto servers
            if message.media:
                sent = await client.send_file(
                    dest_entity,
                    file=message.media,
                    caption=raw_text,
                    formatting_entities=entities,
                    silent=True,
                )
            else:
                # Text message
                sent = await client.send_message(
                    dest_entity,
                    message=raw_text,
                    formatting_entities=entities,
                    silent=True,
                )

            dest_id = sent[0].id if isinstance(sent, list) and sent else getattr(sent, "id", None)
            return CopyResult(success=True, dest_message_id=dest_id)

        except ChatForwardsRestrictedError:
            return CopyResult(
                success=False,
                is_protected=True,
                error="Source channel prohibits message forwarding/copying.",
            )
        except ChatWriteForbiddenError:
            return CopyResult(
                success=False,
                error="Bot/User does not have write permissions in destination archive channel.",
            )
        except RPCError as e:
            logger.warning(f"Server-side copy RPC error for message {message.id}: {e}")
            return CopyResult(success=False, error=f"MTProto error: {e.message if hasattr(e, 'message') else str(e)}")
        except Exception as e:
            logger.error(f"Unexpected copy error for message {message.id}: {e}")
            return CopyResult(success=False, error=str(e))

    @staticmethod
    async def copy_album(
        client: TelegramClient,
        dest_entity: Any,
        album_messages: List[Message],
    ) -> CopyResult:
        """Copies an entire grouped album together, preserving album layout and ordering."""
        if any(getattr(m, "noforwards", False) for m in album_messages):
            return CopyResult(
                success=False,
                is_protected=True,
                error="One or more items in the album have content protection enabled.",
            )

        try:
            files = [m.media for m in album_messages if m.media]
            captions = [getattr(m, "message", None) or getattr(m, "raw_text", None) or "" for m in album_messages if m.media]
            formatting_entities = [list(m.entities) if getattr(m, "entities", None) else [] for m in album_messages if m.media]

            sent = await client.send_file(
                dest_entity,
                file=files,
                caption=captions,
                formatting_entities=formatting_entities if any(formatting_entities) else None,
                silent=True,
            )

            # sent is a list of Messages for albums
            first_id = sent[0].id if isinstance(sent, list) and sent else getattr(sent, "id", None)
            return CopyResult(success=True, dest_message_id=first_id)

        except Exception as e:
            logger.error(f"Album copy failed: {e}")
            return CopyResult(success=False, error=str(e))
