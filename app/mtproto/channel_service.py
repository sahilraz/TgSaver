import asyncio
from collections import defaultdict
import logging
from typing import Any, Dict, List, Optional, Tuple

from telethon import TelegramClient, utils
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.types import Channel, Chat
from app.database.repository import Repository
from app.database.session import get_db_session

logger = logging.getLogger(__name__)

# Global per-(user_id, canonical_id) lock to serialize archive creation and guarantee single channel per source
_creation_locks: Dict[Tuple[int, str], asyncio.Lock] = defaultdict(asyncio.Lock)


class ChannelService:
    @staticmethod
    async def resolve_entity(client: TelegramClient, channel_ref: str) -> Tuple[Optional[Any], Optional[str]]:
        """Resolves a channel entity and returns (entity, title)."""
        try:
            if channel_ref.startswith("-100") or (channel_ref.lstrip("-").isdigit()):
                ref = int(channel_ref)
            else:
                ref = channel_ref

            entity = await client.get_entity(ref)
            title = getattr(entity, "title", getattr(entity, "first_name", str(ref)))
            return entity, title
        except Exception as e:
            logger.error(f"Failed to resolve channel entity {channel_ref}: {e}")
            return None, None

    @staticmethod
    async def get_or_create_archive_channel(
        client: TelegramClient, user_id: int, source_channel_ref: str
    ) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Finds existing mapped archive channel or creates a single dedicated private archive channel.

        Guarantees only ONE archive channel is created per source channel across all posts and batches.
        """
        source_entity, source_title = await ChannelService.resolve_entity(client, source_channel_ref)
        if not source_entity:
            return None, None, f"Source channel '{source_channel_ref}' is inaccessible or restricted."

        source_title = source_title or "Archive"

        # 1. Determine all canonical and alias references for this source channel
        canonical_peer_id = str(utils.get_peer_id(source_entity))  # e.g. -1001234567890
        raw_id = str(getattr(source_entity, "id", ""))
        possible_refs = [canonical_peer_id, raw_id, f"-100{raw_id}", str(source_channel_ref)]
        username = getattr(source_entity, "username", None)
        if username:
            possible_refs.extend([username.lower(), f"@{username.lower()}"])

        lock_key = (user_id, canonical_peer_id)
        async with _creation_locks[lock_key]:
            # 2. Check existing mapping in database using all known aliases
            async with get_db_session() as session:
                repo = Repository(session)
                mapping = await repo.get_mapping_by_any_ref(user_id, possible_refs)

            if mapping:
                dest_id = mapping.destination_channel_id
                dest_entity = None
                try:
                    dest_entity = await client.get_entity(dest_id)
                except Exception:
                    # Refresh dialogs if Telethon entity cache does not have the channel yet
                    try:
                        await client.get_dialogs(limit=50)
                        dest_entity = await client.get_entity(dest_id)
                    except Exception as e:
                        logger.warning(f"Could not resolve destination archive channel {dest_id}: {e}")
                        dest_entity = None

                # If the destination archive is valid, REUSE IT directly!
                if dest_entity is not None or dest_id:
                    # Also ensure canonical mapping is linked in DB if was missing
                    if mapping.source_channel_ref != canonical_peer_id:
                        async with get_db_session() as session:
                            repo = Repository(session)
                            await repo.save_mapping(
                                user_id=user_id,
                                source_channel_ref=canonical_peer_id,
                                destination_channel_id=dest_id,
                                source_title=source_title,
                                destination_title=mapping.destination_title,
                            )
                    return dest_id, source_title, None

            # 3. Search logged-in account's existing channels for a match by title and ownership
            clean_title = f"Archive - {source_title[:55]}"
            norm_clean = clean_title.strip().lower()
            norm_source = source_title.strip().lower()

            try:
                # Scan user's dialogs for an archive channel matching this source name owned by user
                async for dialog in client.iter_dialogs(limit=200):
                    if not dialog.is_channel:
                        continue

                    # Check ownership: creator is True or user has full admin rights
                    is_creator = getattr(dialog.entity, "creator", False)
                    admin_rights = getattr(dialog.entity, "admin_rights", None)
                    can_post = is_creator or (admin_rights and getattr(admin_rights, "post_messages", False))
                    if not can_post:
                        continue

                    d_name = (dialog.name or getattr(dialog.entity, "title", "") or "").strip().lower()
                    # Match exact title, Archive prefix, or source channel title
                    is_match = (
                        d_name == norm_clean
                        or d_name == f"archive - {norm_source}"
                        or (d_name.startswith("archive - ") and norm_source in d_name)
                        or (d_name.startswith("archive ") and norm_source in d_name)
                    )

                    if is_match:
                        dest_channel_id = int(utils.get_peer_id(dialog.entity))
                        logger.info(f"Reusing existing archive channel '{dialog.name}' ({dest_channel_id}) for source '{source_title}'")

                        # Cache mapping for all aliases to avoid searching next time
                        async with get_db_session() as session:
                            repo = Repository(session)
                            for ref in possible_refs:
                                await repo.save_mapping(
                                    user_id=user_id,
                                    source_channel_ref=str(ref).lower(),
                                    destination_channel_id=dest_channel_id,
                                    source_title=source_title,
                                    destination_title=dialog.name,
                                )

                        # Ensure it's in the TgSaver chat folder
                        await ChannelService._ensure_channel_in_folder(client, dialog.entity, "TgSaver")
                        return dest_channel_id, source_title, None
            except Exception as e:
                logger.warning(f"Error inspecting user dialogs for existing archive channels: {e}")

            # 4. Create a single private archive channel for this source only if no match was found anywhere
            try:
                result = await client(
                    CreateChannelRequest(
                        title=clean_title,
                        about=f"Private archive for {source_title}. Managed by TgSaverBot.",
                        megagroup=False,
                    )
                )
                created_channel: Channel = result.chats[0]
                dest_channel_id = int(f"-100{created_channel.id}")

                # Save mapping under canonical peer ID and original reference
                async with get_db_session() as session:
                    repo = Repository(session)
                    await repo.save_mapping(
                        user_id=user_id,
                        source_channel_ref=canonical_peer_id,
                        destination_channel_id=dest_channel_id,
                        source_title=source_title,
                        destination_title=clean_title,
                    )
                    if str(source_channel_ref).lower() != canonical_peer_id.lower():
                        await repo.save_mapping(
                            user_id=user_id,
                            source_channel_ref=str(source_channel_ref).lower(),
                            destination_channel_id=dest_channel_id,
                            source_title=source_title,
                            destination_title=clean_title,
                        )

                # 5. Check for 'TgSaver' chat folder, create if not present, and add new channel
                await ChannelService._ensure_channel_in_folder(client, created_channel, "TgSaver")

                return dest_channel_id, source_title, None
            except Exception as e:
                logger.error(f"Failed to create archive channel: {e}")
                return None, source_title, f"Unable to create private archive channel: {str(e)}"

    @staticmethod
    async def _ensure_channel_in_folder(client: TelegramClient, channel_entity: Any, folder_name: str = "TgSaver") -> None:
        """Checks if a chat folder with folder_name exists; creates it if not, and adds the channel to it."""
        try:
            from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
            from telethon.tl.types import DialogFilter, TextWithEntities

            result = await client(GetDialogFiltersRequest())
            filter_list = getattr(result, "filters", result) if not isinstance(result, list) else result
            filter_list = list(filter_list) if filter_list else []

            input_peer = await client.get_input_entity(channel_entity)
            target_filter = None
            max_id = 1

            for f in filter_list:

                if hasattr(f, "id") and isinstance(f.id, int):
                    if f.id > max_id:
                        max_id = f.id
                title_text = ""
                if hasattr(f, "title"):
                    title_text = f.title if isinstance(f.title, str) else getattr(f.title, "text", "")
                if title_text.strip().lower() == folder_name.strip().lower():
                    target_filter = f
                    break

            if target_filter:
                # Folder already exists - ensure peer is included
                import copy
                include_peers = list(getattr(target_filter, "include_peers", []) or [])
                target_peer_id = utils.get_peer_id(input_peer)
                already_in = any(utils.get_peer_id(p) == target_peer_id for p in include_peers)
                if not already_in:
                    include_peers.append(input_peer)
                    updated_filter = copy.copy(target_filter)
                    updated_filter.include_peers = include_peers
                    if isinstance(updated_filter.title, str):
                        updated_filter.title = TextWithEntities(text=updated_filter.title, entities=[])
                    await client(UpdateDialogFilterRequest(id=target_filter.id, filter=updated_filter))
                    logger.info(f"Added archive channel to existing '{folder_name}' folder (id={target_filter.id}).")

            else:
                # Create new folder
                new_folder_id = max_id + 1
                new_filter = DialogFilter(
                    id=new_folder_id,
                    title=TextWithEntities(text=folder_name, entities=[]),
                    pinned_peers=[],
                    include_peers=[input_peer],
                    exclude_peers=[],
                )
                await client(UpdateDialogFilterRequest(id=new_folder_id, filter=new_filter))
                logger.info(f"Created new '{folder_name}' chat folder (id={new_folder_id}) and added archive channel.")
        except Exception as e:
            logger.warning(f"Could not add channel to '{folder_name}' folder (non-fatal): {e}")
