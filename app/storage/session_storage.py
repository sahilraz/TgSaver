"""Session storage helpers for Telethon MTProto sessions."""

from typing import Optional
from telethon.sessions import StringSession
from app.database.repository import Repository
from app.security.encryption import session_cipher


class DatabaseSessionStorage:
    """Manages Telethon session strings stored encrypted inside PostgreSQL / SQLite."""

    @staticmethod
    async def load_session_string(repo: Repository, telegram_id: int) -> Optional[str]:
        sess_record = await repo.get_user_session(telegram_id)
        if not sess_record or not sess_record.encrypted_session:
            return None
        return session_cipher.decrypt(sess_record.encrypted_session)

    @staticmethod
    async def save_session_string(
        repo: Repository,
        telegram_id: int,
        plain_session_str: str,
        phone_number: Optional[str] = None,
        account_id: Optional[int] = None,
        account_first_name: Optional[str] = None,
    ) -> None:
        encrypted = session_cipher.encrypt(plain_session_str)
        await repo.save_user_session(
            telegram_id=telegram_id,
            encrypted_session=encrypted,
            phone_number=phone_number,
            account_id=account_id,
            account_first_name=account_first_name,
        )
