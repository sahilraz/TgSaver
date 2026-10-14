import asyncio
from datetime import timedelta
import logging
from typing import Dict, Optional
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession
from app.auth.session_manager import client_manager
from app.config import settings
from app.database.models import utc_now
from app.database.repository import Repository
from app.database.session import get_db_session
from app.security.validation import validate_phone_number
from app.storage.session_storage import DatabaseSessionStorage

from telethon.tl.types.auth import (
    SentCodeTypeApp,
    SentCodeTypeSms,
    SentCodeTypeCall,
    SentCodeTypeFlashCall,
    SentCodeTypeMissedCall,
    SentCodeTypeEmailCode,
    SentCodeTypeSetUpEmailRequired,
    SentCodeTypeFragmentSms,
)
from telethon.tl.functions.auth import ResendCodeRequest

logger = logging.getLogger(__name__)


class LoginResult:
    def __init__(
        self,
        success: bool,
        needs_password: bool = False,
        message: str = "",
        error: Optional[str] = None,
        code_type: Optional[str] = None,
    ):
        self.success = success
        self.needs_password = needs_password
        self.message = message
        self.error = error
        self.code_type = code_type


class LoginService:
    def __init__(self):
        self._temp_clients: Dict[int, TelegramClient] = {}
        self._temp_sessions: Dict[int, str] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    def _get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _create_client(self, session_source: Optional[str] = None) -> TelegramClient:
        sess = StringSession(session_source) if session_source else StringSession()
        return TelegramClient(
            sess,
            settings.API_ID,
            settings.API_HASH,
            device_model="Desktop",
            system_version="Windows 11",
            app_version="5.5.0 x64",
            lang_code="en",
            system_lang_code="en",
        )

    async def start_login(self, user_id: int, raw_phone: str) -> LoginResult:
        phone = validate_phone_number(raw_phone)
        if not phone:
            return LoginResult(
                success=False,
                error="Invalid international phone number format. Please provide format like +1234567890.",
            )

        async with self._get_lock(user_id):
            await self._cleanup_temp_client(user_id)

            temp_client = self._create_client()
            await temp_client.connect()

            try:
                sent_code = await temp_client.send_code_request(phone)
                self._temp_clients[user_id] = temp_client
                self._temp_sessions[user_id] = temp_client.session.save()

                expires_at = utc_now() + timedelta(minutes=5)
                async with get_db_session() as session:
                    repo = Repository(session)
                    await repo.set_auth_state(
                        telegram_id=user_id,
                        state="AWAITING_CODE",
                        phone_number=phone,
                        phone_code_hash=sent_code.phone_code_hash,
                        expires_at=expires_at,
                    )

                # Format detailed guidance based on how Telegram delivered the code
                code_type = "unknown"
                if isinstance(sent_code.type, SentCodeTypeApp):
                    code_type = "app"
                    msg = (
                        "📩 <b>Verification Code Sent to Telegram App!</b>\n\n"
                        "Telegram sent your code to your <b>active Telegram session</b> (check your chat list for the official message from <b>Telegram</b>).\n\n"
                        "⚠️ <i>Telegram did NOT send an SMS because you are active on Telegram.</i>\n\n"
                        "Please enter the code here with spaces (e.g., <code>9 0 9 0 9</code>):"
                    )
                elif isinstance(sent_code.type, (SentCodeTypeSms, SentCodeTypeFragmentSms)):
                    code_type = "sms"
                    msg = (
                        "📩 <b>Verification Code Sent via SMS!</b>\n\n"
                        "Telegram sent an SMS code to your phone number.\n\n"
                        "Please enter the code here with spaces (e.g., <code>9 0 9 0 9</code>):"
                    )
                elif isinstance(sent_code.type, SentCodeTypeEmailCode):
                    code_type = "email"
                    msg = (
                        "📩 <b>Verification Code Sent to Email!</b>\n\n"
                        "Telegram sent a verification code to your registered email address.\n\n"
                        "Please enter the code here with spaces (e.g., <code>9 0 9 0 9</code>):"
                    )
                elif isinstance(sent_code.type, SentCodeTypeSetUpEmailRequired):
                    await self._cleanup_temp_client(user_id)
                    return LoginResult(
                        success=False,
                        error="Telegram requires you to configure an email in the official app first. Open Telegram Settings -> Privacy and Security -> Email Login.",
                    )
                elif isinstance(sent_code.type, (SentCodeTypeCall, SentCodeTypeFlashCall, SentCodeTypeMissedCall)):
                    code_type = "call"
                    msg = (
                        "📞 <b>Verification Code via Phone Call!</b>\n\n"
                        "Telegram will call your phone number to give you the code.\n\n"
                        "Please enter the code here with spaces (e.g., <code>9 0 9 0 9</code>):"
                    )
                else:
                    msg = (
                        "📩 <b>Verification code sent by Telegram!</b>\n\n"
                        "Please enter the code here with spaces (e.g., <code>9 0 9 0 9</code>):"
                    )

                return LoginResult(
                    success=True,
                    message=msg,
                    code_type=code_type,
                )

            except PhoneNumberInvalidError:
                await self._cleanup_temp_client(user_id)
                return LoginResult(success=False, error="Telegram reported that this phone number is invalid.")
            except FloodWaitError as e:
                await self._cleanup_temp_client(user_id)
                return LoginResult(
                    success=False,
                    error=f"Telegram flood wait triggered. Please try again after {e.seconds} seconds.",
                )
            except Exception as e:
                await self._cleanup_temp_client(user_id)
                logger.error(f"Error requesting login code for {user_id}: {e}")
                return LoginResult(success=False, error=f"Failed to initiate Telegram login: {str(e)}")

    async def resend_code(self, user_id: int) -> LoginResult:
        async with self._get_lock(user_id):
            temp_client = self._temp_clients.get(user_id)
            if not temp_client and user_id in self._temp_sessions:
                temp_client = self._create_client(self._temp_sessions[user_id])
                await temp_client.connect()
                self._temp_clients[user_id] = temp_client

            if not temp_client:
                return LoginResult(
                    success=False,
                    error="Login session expired or not found. Please click Connect Telegram Account again.",
                )

            async with get_db_session() as session:
                repo = Repository(session)
                auth_state = await repo.get_auth_state(user_id)
                if not auth_state or auth_state.state != "AWAITING_CODE" or not auth_state.phone_number:
                    return LoginResult(success=False, error="No pending login request.")

                phone = auth_state.phone_number
                code_hash = auth_state.phone_code_hash

            try:
                if not temp_client.is_connected():
                    await temp_client.connect()

                res = await temp_client(ResendCodeRequest(phone_number=phone, phone_code_hash=code_hash))
                if hasattr(res, "phone_code_hash") and res.phone_code_hash:
                    async with get_db_session() as session:
                        repo = Repository(session)
                        auth_state = await repo.get_auth_state(user_id)
                        if auth_state:
                            auth_state.phone_code_hash = res.phone_code_hash
                    self._temp_sessions[user_id] = temp_client.session.save()

                return LoginResult(
                    success=True,
                    message="Verification code resent! Please check your SMS or active Telegram app.",
                )
            except FloodWaitError as e:
                return LoginResult(
                    success=False,
                    error=f"Telegram cooldown active: please wait {e.seconds} seconds before requesting SMS.",
                )
            except Exception as e:
                logger.error(f"Error resending code for {user_id}: {e}")
                return LoginResult(success=False, error=f"Could not resend code: {str(e)}")

    async def submit_code(self, user_id: int, code: str) -> LoginResult:
        async with self._get_lock(user_id):
            temp_client = self._temp_clients.get(user_id)
            if not temp_client and user_id in self._temp_sessions:
                temp_client = self._create_client(self._temp_sessions[user_id])
                await temp_client.connect()
                self._temp_clients[user_id] = temp_client

            if not temp_client:
                return LoginResult(
                    success=False,
                    error="Login session expired or not found. Please click Connect Telegram Account again.",
                )

            if not temp_client.is_connected():
                await temp_client.connect()

            async with get_db_session() as session:
                repo = Repository(session)
                auth_state = await repo.get_auth_state(user_id)
                if not auth_state or auth_state.state != "AWAITING_CODE" or not auth_state.phone_number:
                    return LoginResult(success=False, error="No pending login request. Please use /login.")

                phone = auth_state.phone_number
                code_hash = auth_state.phone_code_hash

            clean_code = code.strip().replace(" ", "").replace("-", "")

            try:
                await temp_client.sign_in(phone, clean_code, phone_code_hash=code_hash)
                return await self._finalize_login(user_id, temp_client, phone)

            except SessionPasswordNeededError:
                self._temp_sessions[user_id] = temp_client.session.save()
                async with get_db_session() as session:
                    repo = Repository(session)
                    await repo.set_auth_state(
                        telegram_id=user_id,
                        state="AWAITING_PASSWORD",
                        phone_number=phone,
                        phone_code_hash=code_hash,
                    )
                return LoginResult(
                    success=True,
                    needs_password=True,
                    message="Two-step verification is enabled on this account. Please enter your 2FA password.",
                )
            except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
                return LoginResult(success=False, error=f"Invalid or expired login code: {e}")
            except FloodWaitError as e:
                return LoginResult(success=False, error=f"Telegram flood wait: retry after {e.seconds}s.")
            except Exception as e:
                logger.error(f"Error submitting login code for {user_id}: {e}")
                return LoginResult(success=False, error=f"Login failed: {str(e)}")

    async def submit_password(self, user_id: int, password: str) -> LoginResult:
        async with self._get_lock(user_id):
            temp_client = self._temp_clients.get(user_id)
            if not temp_client and user_id in self._temp_sessions:
                temp_client = self._create_client(self._temp_sessions[user_id])
                await temp_client.connect()
                self._temp_clients[user_id] = temp_client

            if not temp_client:
                return LoginResult(success=False, error="Login session expired. Please restart /login.")

            if not temp_client.is_connected():
                await temp_client.connect()

            async with get_db_session() as session:
                repo = Repository(session)
                auth_state = await repo.get_auth_state(user_id)
                if not auth_state or auth_state.state != "AWAITING_PASSWORD":
                    return LoginResult(success=False, error="Account is not waiting for 2FA password.")
                phone = auth_state.phone_number or ""

            try:
                await temp_client.sign_in(password=password.strip())
                return await self._finalize_login(user_id, temp_client, phone)
            except PasswordHashInvalidError:
                return LoginResult(success=False, error="Incorrect two-step verification password.")
            except Exception as e:
                logger.error(f"Error submitting password for {user_id}: {e}")
                return LoginResult(success=False, error=f"Failed to verify password: {str(e)}")

    async def _finalize_login(self, user_id: int, client: TelegramClient, phone: str) -> LoginResult:
        try:
            me = await client.get_me()
            session_str = client.session.save()

            async with get_db_session() as session:
                repo = Repository(session)
                await DatabaseSessionStorage.save_session_string(
                    repo=repo,
                    telegram_id=user_id,
                    plain_session_str=session_str,
                    phone_number=phone,
                    account_id=me.id,
                    account_first_name=me.first_name,
                )
                await repo.clear_auth_state(user_id)

            self._temp_clients.pop(user_id, None)
            self._temp_sessions.pop(user_id, None)
            client_manager.set_active_client(user_id, client)

            return LoginResult(
                success=True,
                message=f"Connected successfully to account: {me.first_name} (ID: {me.id})!",
            )
        except Exception as e:
            logger.error(f"Error finalizing login for {user_id}: {e}")
            await self._cleanup_temp_client(user_id)
            return LoginResult(success=False, error=f"Failed to finalize session: {str(e)}")

    async def cancel_login(self, user_id: int) -> bool:
        async with self._get_lock(user_id):
            await self._cleanup_temp_client(user_id)
            async with get_db_session() as session:
                repo = Repository(session)
                await repo.clear_auth_state(user_id)
        return True

    async def _cleanup_temp_client(self, user_id: int) -> None:
        self._temp_sessions.pop(user_id, None)
        client = self._temp_clients.pop(user_id, None)
        if client:
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass

    async def disconnect_account(self, user_id: int) -> bool:
        await client_manager.close_client(user_id)
        async with get_db_session() as session:
            repo = Repository(session)
            user = await repo.get_user(user_id)
            if user:
                user.is_connected = False
        return True

    async def logout_completely(self, user_id: int) -> bool:
        client = await client_manager.get_client(user_id)
        if client:
            try:
                await client.log_out()
            except Exception as e:
                logger.warning(f"Error during client.log_out for user {user_id}: {e}")
            finally:
                await client_manager.close_client(user_id)

        async with get_db_session() as session:
            repo = Repository(session)
            await repo.delete_user_session(user_id)

        return True


login_service = LoginService()
