import asyncio
import hashlib
import inspect
import logging
import math
import os
from typing import Any, AsyncGenerator, BinaryIO, Callable, List, Optional, Tuple, Union

from telethon import TelegramClient, helpers, utils
from telethon.crypto import AuthKey
from telethon.network import MTProtoSender
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import (
    GetFileRequest,
    SaveBigFilePartRequest,
    SaveFilePartRequest,
)
from telethon.tl.types import (
    Document,
    InputDocumentFileLocation,
    InputFile,
    InputFileBig,
    InputFileLocation,
    InputPeerPhotoFileLocation,
    InputPhotoFileLocation,
    TypeInputFile,
)

logger = logging.getLogger(__name__)

TypeLocation = Union[
    Document,
    InputDocumentFileLocation,
    InputPeerPhotoFileLocation,
    InputFileLocation,
    InputPhotoFileLocation,
]


class DownloadSender:
    def __init__(
        self,
        client: TelegramClient,
        sender: MTProtoSender,
        file: TypeLocation,
        offset: int,
        limit: int,
        stride: int,
        count: int,
    ) -> None:
        self.client = client
        self.sender = sender
        self.request = GetFileRequest(file, offset=offset, limit=limit)
        self.stride = stride
        self.remaining = count

    async def next(self) -> Optional[bytes]:
        if not self.remaining:
            return None
        result = await self.client._call(self.sender, self.request)
        self.remaining -= 1
        self.request.offset += self.stride
        return result.bytes

    async def disconnect(self) -> None:
        await self.sender.disconnect()


class UploadSender:
    def __init__(
        self,
        client: TelegramClient,
        sender: MTProtoSender,
        file_id: int,
        part_count: int,
        big: bool,
        index: int,
        stride: int,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.client = client
        self.sender = sender
        self.part_count = part_count
        if big:
            self.request = SaveBigFilePartRequest(file_id, index, part_count, b"")
        else:
            self.request = SaveFilePartRequest(file_id, index, b"")
        self.stride = stride
        self.previous: Optional[asyncio.Task] = None
        self.loop = loop

    async def next(self, data: bytes) -> None:
        if self.previous:
            await self.previous
        self.previous = self.loop.create_task(self._next(data))

    async def _next(self, data: bytes) -> None:
        self.request.bytes = data
        await self.client._call(self.sender, self.request)
        self.request.file_part += self.stride

    async def disconnect(self) -> None:
        if self.previous:
            await self.previous
        await self.sender.disconnect()


class ParallelTransferrer:
    def __init__(self, client: TelegramClient, dc_id: Optional[int] = None) -> None:
        self.client = client
        self.loop = self.client.loop
        self.dc_id = dc_id or self.client.session.dc_id
        self.auth_key = None if dc_id and self.client.session.dc_id != dc_id else self.client.session.auth_key
        self.senders: Optional[List[Union[DownloadSender, UploadSender]]] = None
        self.upload_ticker = 0

    async def _cleanup(self) -> None:
        if self.senders:
            await asyncio.gather(*[sender.disconnect() for sender in self.senders], return_exceptions=True)
            self.senders = None

    @staticmethod
    def _get_connection_count(file_size: int, max_count: int = 12, full_size: int = 100 * 1024 * 1024) -> int:
        if file_size > full_size:
            return max_count
        return max(2, math.ceil((file_size / full_size) * max_count))

    async def _create_sender(self) -> MTProtoSender:
        dc = await self.client._get_dc(self.dc_id)
        sender = MTProtoSender(self.auth_key, loggers=self.client._log)
        await sender.connect(
            self.client._connection(
                dc.ip_address,
                dc.port,
                dc.id,
                loggers=self.client._log,
                proxy=self.client._proxy,
            )
        )
        if not self.auth_key:
            auth = await self.client(ExportAuthorizationRequest(self.dc_id))
            self.client._init_request.query = ImportAuthorizationRequest(id=auth.id, bytes=auth.bytes)
            req = InvokeWithLayerRequest(LAYER, self.client._init_request)
            await sender.send(req)
            self.auth_key = sender.auth_key
        return sender

    async def _create_download_sender(
        self, file: TypeLocation, index: int, part_size: int, stride: int, part_count: int
    ) -> DownloadSender:
        return DownloadSender(self.client, await self._create_sender(), file, index * part_size, part_size, stride, part_count)

    async def _init_download(
        self, connections: int, file: TypeLocation, part_count: int, part_size: int
    ) -> None:
        minimum, remainder = divmod(part_count, connections)

        def get_part_count() -> int:
            nonlocal remainder
            if remainder > 0:
                remainder -= 1
                return minimum + 1
            return minimum

        first_sender = await self._create_download_sender(file, 0, part_size, connections * part_size, get_part_count())
        other_senders = await asyncio.gather(
            *[self._create_download_sender(file, i, part_size, connections * part_size, get_part_count()) for i in range(1, connections)]
        )
        self.senders = [first_sender, *other_senders]

    async def download(
        self,
        file: TypeLocation,
        file_size: int,
        part_size: int = 512 * 1024,
        connection_count: Optional[int] = None,
    ) -> AsyncGenerator[bytes, None]:
        connection_count = connection_count or self._get_connection_count(file_size)
        part_count = math.ceil(file_size / part_size)
        await self._init_download(connection_count, file, part_count, part_size)

        part = 0
        try:
            while part < part_count:
                tasks = [self.loop.create_task(s.next()) for s in self.senders]
                for task in tasks:
                    data = await task
                    if not data:
                        break
                    yield data
                    part += 1
        finally:
            await self._cleanup()

    async def _create_upload_sender(
        self, file_id: int, part_count: int, big: bool, index: int, stride: int
    ) -> UploadSender:
        return UploadSender(
            self.client,
            await self._create_sender(),
            file_id,
            part_count,
            big,
            index,
            stride,
            loop=self.loop,
        )

    async def _init_upload(self, connections: int, file_id: int, part_count: int, big: bool) -> None:
        first_sender = await self._create_upload_sender(file_id, part_count, big, 0, connections)
        other_senders = await asyncio.gather(
            *[self._create_upload_sender(file_id, part_count, big, i, connections) for i in range(1, connections)]
        )
        self.senders = [first_sender, *other_senders]

    async def init_upload(
        self,
        file_id: int,
        file_size: int,
        part_size: int = 512 * 1024,
        connection_count: Optional[int] = None,
    ) -> Tuple[int, int, bool]:
        connection_count = connection_count or self._get_connection_count(file_size)
        part_count = (file_size + part_size - 1) // part_size
        is_large = file_size > 10 * 1024 * 1024
        await self._init_upload(connection_count, file_id, part_count, is_large)
        return part_size, part_count, is_large

    async def upload(self, part: bytes) -> None:
        await self.senders[self.upload_ticker].next(part)
        self.upload_ticker = (self.upload_ticker + 1) % len(self.senders)

    async def finish_upload(self) -> None:
        await self._cleanup()


async def fast_upload_file(
    client: TelegramClient,
    file_path: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> TypeInputFile:
    """Uploads a local file using parallel 512KB MTProto connections for maximum throughput."""
    file_size = os.path.getsize(file_path)
    file_id = helpers.generate_random_long()
    part_size = 512 * 1024  # Max 512 KB chunk
    is_large = file_size > 10 * 1024 * 1024

    uploader = ParallelTransferrer(client)
    part_size, part_count, is_large = await uploader.init_upload(file_id, file_size, part_size=part_size)
    hash_md5 = hashlib.md5() if not is_large else None

    sent_bytes = 0
    buffer = bytearray()

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            if hash_md5:
                hash_md5.update(chunk)
            buffer.extend(chunk)

            while len(buffer) >= part_size:
                part_data = bytes(buffer[:part_size])
                del buffer[:part_size]
                await uploader.upload(part_data)
                sent_bytes += len(part_data)
                if progress_callback:
                    res = progress_callback(sent_bytes, file_size)
                    if inspect.isawaitable(res):
                        await res

        if len(buffer) > 0:
            part_data = bytes(buffer)
            buffer.clear()
            await uploader.upload(part_data)
            sent_bytes += len(part_data)
            if progress_callback:
                res = progress_callback(sent_bytes, file_size)
                if inspect.isawaitable(res):
                    await res

    await uploader.finish_upload()

    base_name = os.path.basename(file_path)
    if is_large:
        return InputFileBig(id=file_id, parts=part_count, name=base_name)
    else:
        return InputFile(id=file_id, parts=part_count, name=base_name, md5_checksum=hash_md5.hexdigest())


async def fast_download_file(
    client: TelegramClient,
    location: Any,
    file_path: str,
    file_size: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Downloads a file using parallel MTProto connections with 512KB chunks directly to disk."""
    dc_id, input_location = utils.get_input_location(location)
    downloader = ParallelTransferrer(client, dc_id=dc_id)

    downloaded_bytes = 0
    with open(file_path, "wb") as f:
        async for chunk in downloader.download(input_location, file_size=file_size, part_size=512 * 1024):
            f.write(chunk)
            downloaded_bytes += len(chunk)
            if progress_callback:
                res = progress_callback(downloaded_bytes, file_size)
                if inspect.isawaitable(res):
                    await res

    return file_path
