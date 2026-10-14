"""Authenticated encryption for session strings and sensitive tokens at rest.

Uses cryptography.fernet.Fernet (AES-128-CBC with HMAC-SHA256 authenticated encryption).
"""

from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from app.config import settings


class SessionEncryptionService:
    def __init__(self, key: Optional[str] = None):
        self._key = (key or settings.ENCRYPTION_KEY).encode("utf-8")
        self._fernet = Fernet(self._key)

    def encrypt(self, plain_text: str) -> str:
        """Encrypt plain text session string into a safe ascii ciphertext token."""
        if not plain_text:
            return ""
        return self._fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def decrypt(self, cipher_text: str) -> str:
        """Decrypt ciphertext token back to plain text session string."""
        if not cipher_text:
            return ""
        try:
            return self._fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt session: invalid key or corrupted payload") from exc

    def rotate(self, cipher_text: str, new_key: str) -> str:
        """Re-encrypt ciphertext with a new encryption key."""
        plain = self.decrypt(cipher_text)
        new_fernet = Fernet(new_key.encode("utf-8"))
        return new_fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


session_cipher = SessionEncryptionService()
