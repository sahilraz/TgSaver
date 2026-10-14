"""Repository layer for database operations with strict user scoping."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import (
    ArchiveItem,
    ArchiveMapping,
    AuthState,
    BatchJob,
    User,
    UserSession,
    UserSettings,
    utc_now,
)
from app.security.ownership import verify_user_ownership


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------
    # User Management
    # -------------------------------------------------------------
    async def get_or_create_user(
        self, telegram_id: int, username: Optional[str] = None, first_name: Optional[str] = None
    ) -> User:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_connected=False,
            )
            self.session.add(user)
            # Create default user settings
            settings = UserSettings(user_id=telegram_id)
            self.session.add(settings)
            await self.session.flush()
        else:
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            await self.session.flush()

        return user

    async def get_user(self, telegram_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    # -------------------------------------------------------------
    # Session & Authentication State
    # -------------------------------------------------------------
    async def get_user_session(self, telegram_id: int) -> Optional[UserSession]:
        stmt = select(UserSession).where(UserSession.telegram_id == telegram_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_user_session(
        self,
        telegram_id: int,
        encrypted_session: str,
        phone_number: Optional[str] = None,
        account_id: Optional[int] = None,
        account_first_name: Optional[str] = None,
    ) -> UserSession:
        user_sess = await self.get_user_session(telegram_id)
        now = utc_now()
        if not user_sess:
            user_sess = UserSession(
                telegram_id=telegram_id,
                encrypted_session=encrypted_session,
                phone_number=phone_number,
                account_id=account_id,
                account_first_name=account_first_name,
                connected_at=now,
                last_checked_at=now,
            )
            self.session.add(user_sess)
        else:
            user_sess.encrypted_session = encrypted_session
            if phone_number:
                user_sess.phone_number = phone_number
            if account_id:
                user_sess.account_id = account_id
            if account_first_name:
                user_sess.account_first_name = account_first_name
            user_sess.connected_at = now
            user_sess.last_checked_at = now

        # Update User connection flag
        await self.session.execute(
            update(User).where(User.telegram_id == telegram_id).values(is_connected=True)
        )
        await self.session.flush()
        return user_sess

    async def delete_user_session(self, telegram_id: int) -> bool:
        """Deletes encrypted session and marks user disconnected."""
        await self.session.execute(
            delete(UserSession).where(UserSession.telegram_id == telegram_id)
        )
        await self.session.execute(
            update(User).where(User.telegram_id == telegram_id).values(is_connected=False)
        )
        await self.clear_auth_state(telegram_id)
        await self.session.flush()
        return True

    async def get_auth_state(self, telegram_id: int) -> Optional[AuthState]:
        stmt = select(AuthState).where(AuthState.telegram_id == telegram_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def set_auth_state(
        self,
        telegram_id: int,
        state: str,
        phone_number: Optional[str] = None,
        phone_code_hash: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> AuthState:
        auth_state = await self.get_auth_state(telegram_id)
        now = utc_now()
        if not auth_state:
            auth_state = AuthState(
                telegram_id=telegram_id,
                state=state,
                phone_number=phone_number,
                phone_code_hash=phone_code_hash,
                created_at=now,
                expires_at=expires_at,
            )
            self.session.add(auth_state)
        else:
            auth_state.state = state
            if phone_number is not None:
                auth_state.phone_number = phone_number
            if phone_code_hash is not None:
                auth_state.phone_code_hash = phone_code_hash
            auth_state.expires_at = expires_at
        await self.session.flush()
        return auth_state

    async def clear_auth_state(self, telegram_id: int) -> None:
        await self.session.execute(
            delete(AuthState).where(AuthState.telegram_id == telegram_id)
        )
        await self.session.flush()

    # -------------------------------------------------------------
    # Archive Channel Mappings
    # -------------------------------------------------------------
    async def get_mapping(self, user_id: int, source_channel_ref: str) -> Optional[ArchiveMapping]:
        stmt = select(ArchiveMapping).where(
            ArchiveMapping.user_id == user_id,
            func.lower(ArchiveMapping.source_channel_ref) == str(source_channel_ref).lower(),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_mapping_by_any_ref(self, user_id: int, possible_refs: List[str]) -> Optional[ArchiveMapping]:
        clean_refs = [str(r).lower() for r in possible_refs if r]
        if not clean_refs:
            return None
        stmt = (
            select(ArchiveMapping)
            .where(
                ArchiveMapping.user_id == user_id,
                func.lower(ArchiveMapping.source_channel_ref).in_(clean_refs),
            )
            .order_by(ArchiveMapping.id.asc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def list_mappings(self, user_id: int) -> List[ArchiveMapping]:
        stmt = select(ArchiveMapping).where(ArchiveMapping.user_id == user_id).order_by(ArchiveMapping.id.desc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save_mapping(
        self,
        user_id: int,
        source_channel_ref: str,
        destination_channel_id: int,
        source_title: Optional[str] = None,
        destination_title: Optional[str] = None,
    ) -> ArchiveMapping:
        ref_str = str(source_channel_ref).lower()
        mapping = await self.get_mapping(user_id, ref_str)
        if not mapping:
            mapping = ArchiveMapping(
                user_id=user_id,
                source_channel_ref=ref_str,
                destination_channel_id=destination_channel_id,
                source_title=source_title,
                destination_title=destination_title,
            )
            self.session.add(mapping)
        else:
            mapping.destination_channel_id = destination_channel_id
            if source_title:
                mapping.source_title = source_title
            if destination_title:
                mapping.destination_title = destination_title
        await self.session.flush()
        return mapping

    # -------------------------------------------------------------
    # Duplicate Detection & Processed Items
    # -------------------------------------------------------------
    async def is_message_archived(
        self, user_id: int, source_channel_refs: List[str] | str, source_message_id: int
    ) -> bool:
        refs = [str(source_channel_refs)] if isinstance(source_channel_refs, str) else [str(r) for r in source_channel_refs]
        stmt = select(ArchiveItem.id).where(
            ArchiveItem.user_id == user_id,
            ArchiveItem.source_channel_ref.in_(refs),
            ArchiveItem.source_message_id == source_message_id,
            ArchiveItem.status == "COMPLETED",
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none() is not None


    # -------------------------------------------------------------
    # Batch Jobs & Archive Items
    # -------------------------------------------------------------
    async def create_batch_job(self, user_id: int, items_data: List[dict]) -> BatchJob:
        batch = BatchJob(
            user_id=user_id,
            status="QUEUED",
            total_items=len(items_data),
            completed_items=0,
            failed_items=0,
            skipped_items=0,
            bytes_transferred=0,
        )
        self.session.add(batch)
        await self.session.flush()

        for item in items_data:
            archive_item = ArchiveItem(
                batch_id=batch.id,
                user_id=user_id,
                source_url=item["source_url"],
                source_channel_ref=str(item["source_channel_ref"]),
                source_message_id=item["source_message_id"],
                status="QUEUED",
            )
            self.session.add(archive_item)

        await self.session.flush()
        return batch

    async def get_batch_job(self, batch_id: str, requesting_user_id: Optional[int] = None) -> Optional[BatchJob]:
        stmt = select(BatchJob).where(BatchJob.id == batch_id)
        res = await self.session.execute(stmt)
        batch = res.scalar_one_or_none()
        if batch and requesting_user_id is not None:
            verify_user_ownership(batch.user_id, requesting_user_id, "batch job")
        return batch

    async def get_batch_items(self, batch_id: str, requesting_user_id: Optional[int] = None) -> List[ArchiveItem]:
        batch = await self.get_batch_job(batch_id, requesting_user_id)
        if not batch:
            return []
        stmt = select(ArchiveItem).where(ArchiveItem.batch_id == batch_id).order_by(ArchiveItem.id.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_user_batches(self, user_id: int, limit: int = 10, offset: int = 0) -> List[BatchJob]:
        stmt = (
            select(BatchJob)
            .where(BatchJob.user_id == user_id)
            .order_by(BatchJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def cancel_batch_job(self, batch_id: str, requesting_user_id: int) -> bool:
        batch = await self.get_batch_job(batch_id, requesting_user_id)
        if not batch:
            return False
        if batch.status in ("QUEUED", "RUNNING"):
            batch.status = "CANCELLED"
            batch.finished_at = utc_now()
            # Cancel queued items
            await self.session.execute(
                update(ArchiveItem)
                .where(ArchiveItem.batch_id == batch_id, ArchiveItem.status == "QUEUED")
                .values(status="CANCELLED")
            )
            await self.session.flush()
            return True
        return False

    async def get_user_statistics(self, user_id: int) -> Dict[str, Any]:
        """Calculates user statistics: total processed, bytes transferred, completed jobs."""
        batches_stmt = select(
            func.count(BatchJob.id),
            func.sum(BatchJob.completed_items),
            func.sum(BatchJob.failed_items),
            func.sum(BatchJob.bytes_transferred),
        ).where(BatchJob.user_id == user_id)
        res = await self.session.execute(batches_stmt)
        row = res.one()

        total_batches = row[0] or 0
        total_completed = row[1] or 0
        total_failed = row[2] or 0
        total_bytes = row[3] or 0

        mappings_stmt = select(func.count(ArchiveMapping.id)).where(ArchiveMapping.user_id == user_id)
        mappings_res = await self.session.execute(mappings_stmt)
        total_mappings = mappings_res.scalar_one() or 0

        return {
            "total_batches": total_batches,
            "total_completed": total_completed,
            "total_failed": total_failed,
            "total_bytes": total_bytes,
            "total_mappings": total_mappings,
        }
