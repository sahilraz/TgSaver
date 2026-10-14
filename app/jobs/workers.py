import asyncio
import logging
import time
from typing import Optional
from telethon import utils
from telethon.errors import FloodWaitError

from app.auth.session_manager import client_manager
from app.config import settings
from app.database.models import utc_now
from app.database.repository import Repository
from app.database.session import get_db_session
from app.jobs.queue import job_queue
from app.mtproto.channel_service import ChannelService
from app.mtproto.copy_service import CopyService
from app.mtproto.message_service import MessageService
from app.mtproto.transfer_service import TransferService

logger = logging.getLogger(__name__)


class BatchWorker:
    def __init__(self):
        self._running = False
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        self._notify_callback = None

    def set_notifier(self, callback):
        self._notify_callback = callback

    async def start(self):
        self._running = True
        logger.info("BatchWorker started.")
        # Run retention cleanup in background daily
        asyncio.create_task(self._retention_cleanup_loop())

        while self._running:
            try:
                batch_id = await job_queue.get_next_job()
                if not batch_id:
                    await asyncio.sleep(1.0)
                    continue

                await self._semaphore.acquire()
                asyncio.create_task(self._process_batch_wrapper(batch_id))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(2.0)

    async def _retention_cleanup_loop(self):
        """Periodically purge transfer and channel records older than 30 days."""
        while self._running:
            try:
                async with get_db_session() as session:
                    repo = Repository(session)
                    deleted_count = await repo.cleanup_old_records(days=30)
                    if deleted_count > 0:
                        logger.info(f"Cleaned up {deleted_count} expired records older than 30 days.")
            except Exception as e:
                logger.error(f"Error in data retention cleanup job: {e}")

            # Sleep 24 hours between cleanup runs
            await asyncio.sleep(86400)

    async def stop(self):
        self._running = False
        logger.info("BatchWorker stopping.")

    async def _process_batch_wrapper(self, batch_id: str):
        try:
            await self._process_batch(batch_id)
        except Exception as e:
            logger.error(f"Unexpected error in worker processing batch {batch_id}: {e}", exc_info=True)
        finally:
            async with job_queue._lock:
                job_queue._in_flight.discard(batch_id)
            self._semaphore.release()

    async def _process_batch(self, batch_id: str):
        user_id = 0
        try:
            async with get_db_session() as session:
                repo = Repository(session)
                batch = await repo.get_batch_job(batch_id)
                if not batch or batch.status not in ("QUEUED", "RUNNING"):
                    return
                user_id = batch.user_id
                batch.status = "RUNNING"
                batch.started_at = utc_now()
                items = await repo.get_batch_items(batch_id)

            client = await client_manager.get_client(user_id)
            if not client:
                async with get_db_session() as session:
                    repo = Repository(session)
                    batch = await repo.get_batch_job(batch_id)
                    if batch:
                        batch.status = "FAILED"
                        batch.error_message = "Telegram account is not connected or authorization expired."
                        batch.finished_at = utc_now()
                return

            completed_count = 0
            failed_count = 0
            skipped_count = 0
            total_bytes = 0
            start_time = time.monotonic()

            for item in items:
                async with get_db_session() as session:
                    repo = Repository(session)
                    current_batch = await repo.get_batch_job(batch_id)
                    if current_batch and current_batch.status == "CANCELLED":
                        logger.info(f"Batch {batch_id} was cancelled by user.")
                        break

                dest_channel_id, source_title, channel_err = await ChannelService.get_or_create_archive_channel(
                    client, user_id, item.source_channel_ref
                )
                if not dest_channel_id:
                    async with get_db_session() as session:
                        repo = Repository(session)
                        item_obj = (await repo.get_batch_items(batch_id))[items.index(item)]
                        item_obj.status = "FAILED"
                        item_obj.error_category = "CHANNEL_ERROR"
                        item_obj.error_detail = channel_err
                    failed_count += 1
                    continue

                source_entity, _ = await ChannelService.resolve_entity(client, item.source_channel_ref)
                if not source_entity:
                    async with get_db_session() as session:
                        repo = Repository(session)
                        item_obj = (await repo.get_batch_items(batch_id))[items.index(item)]
                        item_obj.status = "FAILED"
                        item_obj.error_category = "SOURCE_INACCESSIBLE"
                    failed_count += 1
                    continue

                canonical_source_id = str(utils.get_peer_id(source_entity))
                raw_source_id = str(getattr(source_entity, "id", ""))
                possible_source_refs = [canonical_source_id, raw_source_id, f"-100{raw_source_id}", str(item.source_channel_ref)]
                src_username = getattr(source_entity, "username", None)
                if src_username:
                    possible_source_refs.extend([src_username.lower(), f"@{src_username.lower()}"])

                # Check duplicates across all known channel aliases
                async with get_db_session() as session:
                    repo = Repository(session)
                    if await repo.is_message_archived(user_id, possible_source_refs, item.source_message_id):
                        item_obj = (await repo.get_batch_items(batch_id))[items.index(item)]
                        item_obj.status = "SKIPPED"
                        item_obj.error_category = "DUPLICATE"
                        item_obj.error_detail = "Message was already processed previously."
                        skipped_count += 1
                        continue

                msg = await MessageService.get_message(client, source_entity, item.source_message_id)
                if not msg:
                    async with get_db_session() as session:
                        repo = Repository(session)
                        item_obj = (await repo.get_batch_items(batch_id))[items.index(item)]
                        item_obj.status = "FAILED"
                        item_obj.error_category = "MESSAGE_NOT_FOUND"
                    failed_count += 1
                    continue

                dest_entity, _ = await ChannelService.resolve_entity(client, str(dest_channel_id))
                meta = MessageService.extract_metadata(msg)
                copy_res = None

                # 1. Attempt zero-bandwidth server-side copy if not protected
                if not meta.noforwards:
                    copy_res = await CopyService.copy_message(client, dest_entity, msg)

                if copy_res and copy_res.success:
                    completed_count += 1
                    async with get_db_session() as session:
                        repo = Repository(session)
                        item_obj = (await repo.get_batch_items(batch_id))[items.index(item)]
                        item_obj.status = "COMPLETED"
                        item_obj.method = "COPY"
                        item_obj.source_channel_ref = canonical_source_id
                        item_obj.destination_channel_id = dest_channel_id
                        item_obj.destination_message_id = copy_res.dest_message_id
                        item_obj.file_name = meta.file_name
                        item_obj.file_size = meta.file_size
                        item_obj.finished_at = utc_now()
                else:
                    # 2. Fallback: Channel has copying disabled or message is protected
                    logger.info(
                        f"Message {item.source_message_id} copy restricted or prohibited. "
                        f"Triggering high-speed download & re-upload fallback..."
                    )

                    async def on_transfer_progress(cur_bytes: int, tot_bytes: int, phase: str, speed: float):
                        if self._notify_callback:
                            await self._notify_callback(
                                batch_id=batch_id,
                                user_id=user_id,
                                completed=completed_count,
                                failed=failed_count,
                                skipped=skipped_count,
                                total=len(items),
                                bytes_transferred=total_bytes + cur_bytes,
                                elapsed=time.monotonic() - start_time,
                            )

                    transfer_res = await TransferService.transfer_media(
                        client, dest_entity, msg, on_progress=on_transfer_progress
                    )
                    if transfer_res.success:
                        completed_count += 1
                        total_bytes += transfer_res.bytes_transferred
                        async with get_db_session() as session:
                            repo = Repository(session)
                            item_obj = (await repo.get_batch_items(batch_id))[items.index(item)]
                            item_obj.status = "COMPLETED"
                            item_obj.method = "TRANSFER"
                            item_obj.source_channel_ref = canonical_source_id
                            item_obj.destination_channel_id = dest_channel_id
                            item_obj.destination_message_id = transfer_res.dest_message_id
                            item_obj.file_name = meta.file_name
                            item_obj.file_size = transfer_res.bytes_transferred
                            item_obj.finished_at = utc_now()
                    else:
                        failed_count += 1
                        async with get_db_session() as session:
                            repo = Repository(session)
                            item_obj = (await repo.get_batch_items(batch_id))[items.index(item)]
                            item_obj.status = "FAILED"
                            item_obj.error_category = "TRANSFER_FAILED"
                            item_obj.error_detail = transfer_res.error

                async with get_db_session() as session:
                    repo = Repository(session)
                    b = await repo.get_batch_job(batch_id)
                    if b and b.status != "CANCELLED":
                        b.completed_items = completed_count
                        b.failed_items = failed_count
                        b.skipped_items = skipped_count
                        b.bytes_transferred = total_bytes

                if self._notify_callback:
                    await self._notify_callback(
                        batch_id=batch_id,
                        user_id=user_id,
                        completed=completed_count,
                        failed=failed_count,
                        skipped=skipped_count,
                        total=len(items),
                        bytes_transferred=total_bytes,
                        elapsed=time.monotonic() - start_time,
                    )

            final_dest_channel_id = None
            final_dest_msg_id = None
            async with get_db_session() as session:
                repo = Repository(session)
                b = await repo.get_batch_job(batch_id)
                if b and b.status != "CANCELLED":
                    if failed_count == 0:
                        b.status = "COMPLETED"
                    elif completed_count > 0:
                        b.status = "PARTIALLY_COMPLETED"
                    else:
                        b.status = "FAILED"
                    b.finished_at = utc_now()
                    b.completed_items = completed_count
                    b.failed_items = failed_count
                    b.skipped_items = skipped_count
                    b.bytes_transferred = total_bytes

                items_in_batch = await repo.get_batch_items(batch_id)
                for itm in items_in_batch:
                    if itm.status == "COMPLETED" and itm.destination_channel_id and itm.destination_message_id:
                        final_dest_channel_id = itm.destination_channel_id
                        final_dest_msg_id = itm.destination_message_id
                        break

            if self._notify_callback:
                final_status = "COMPLETED" if failed_count == 0 else ("PARTIALLY_COMPLETED" if completed_count > 0 else "FAILED")
                await self._notify_callback(
                    batch_id=batch_id,
                    user_id=user_id,
                    completed=completed_count,
                    failed=failed_count,
                    skipped=skipped_count,
                    total=len(items),
                    bytes_transferred=total_bytes,
                    elapsed=time.monotonic() - start_time,
                    final_status=final_status,
                    destination_channel_id=final_dest_channel_id,
                    destination_message_id=final_dest_msg_id,
                )


        except FloodWaitError as e:
            logger.warning(f"Telegram FloodWaitError in worker: {e.seconds}s")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Unexpected error in worker processing batch {batch_id}: {e}")
        finally:
            if user_id:
                await job_queue.release_job(batch_id, user_id)


batch_worker = BatchWorker()
