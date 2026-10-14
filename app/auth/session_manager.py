import asyncio
import logging
from typing import Dict, Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from app.config import settings
from app.database.session import get_db_session
from app.database.repository import Repository
from app.storage.session_storage import DatabaseSessionStorage

logger = logging.getLogger(__name__)


class MTProtoClientManager:
    """Maintains active, connected Telethon user clients with concurrency isolation."""

    def __init__(self):
        self._clients: Dict[int, TelegramClient] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    async def get_client(self, user_id: int) -> Optional[TelegramClient]:
        """Retrieves or initializes a connected TelegramClient for the given user."""
        async with self._get_user_lock(user_id):
            client = self._clients.get(user_id)
            if client and client.is_connected():
                return client

            # Load encrypted session string from database
            async with get_db_session() as session:
                repo = Repository(session)
                session_str = await DatabaseSessionStorage.load_session_string(repo, user_id)

            if not session_str:
                return None

            try:
                client = TelegramClient(
                    StringSession(session_str),
                    settings.API_ID,
                    settings.API_HASH,
                    device_model="TgSaverBot Ultra Engine",
                    system_version="Linux/Docker/VPS",
                    app_version="1.0.0",
                )
                await client.connect()
                if not await client.is_user_authorized():
                    await client.disconnect()
                    return None

                self._clients[user_id] = client
                return client
            except Exception as e:
                logger.error(f"Failed to connect client for user {user_id}: {e}")
                return None

    def set_active_client(self, user_id: int, client: TelegramClient) -> None:
        """Stores an authenticated client in the active registry."""
        self._clients[user_id] = client

    async def close_client(self, user_id: int) -> None:
        async with self._get_user_lock(user_id):
            client = self._clients.pop(user_id, None)
            if client:
                try:
                    if client.is_connected():
                        await client.disconnect()
                except Exception as e:
                    logger.warning(f"Error disconnecting client {user_id}: {e}")

    async def close_all(self) -> None:
        for user_id in list(self._clients.keys()):
            await self.close_client(user_id)


client_manager = MTProtoClientManager()
