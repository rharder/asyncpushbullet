"""
Asynchronous listeners for connecting to Pushbullet's realtime event stream.

Pushbullet's API: https://docs.pushbullet.com/#realtime-event-stream
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

import aiohttp  # pip install aiohttp

from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.websocket_client import WebsocketClient


__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'


class PushListener2:

    def __init__(self, account: AsyncPushbullet,
                 filter_inactive: bool = True,
                 filter_dismissed: bool = True,
                 filter_device_nickname: str = None):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.account = account  # type: AsyncPushbullet
        self._last_update = 0  # type: float
        self._filter_inactive = filter_inactive  # type: bool
        self._filter_dismissed = filter_dismissed  # type: bool
        self._filter_device_nickname = filter_device_nickname  # type: str
        self._ws_client = None  # type: WebsocketClient
        self._loop = None  # type: asyncio.BaseEventLoop
        self._queue = None  # type: asyncio.Queue

    async def close(self):
        await self._ws_client.close()

    async def __aenter__(self):
        self._queue = asyncio.Queue()

        async def _listen_for_pushes(_wc: WebsocketClient):
            try:

                # Stay here for a while receiving messages
                async for msg in _wc:
                    await self._process_websocket_message(msg)

            except Exception as e:
                sai = StopAsyncIteration(e)
                await self._queue.put(sai)
            else:
                sai = StopAsyncIteration()
                await self._queue.put(sai)

        session = await self.account.aio_session()
        wc = WebsocketClient(url=WEBSOCKET_URL + self.account.api_key,
                             proxy=self.account.proxy,
                             session=session)
        self._ws_client = await wc.__aenter__()
        asyncio.create_task(_listen_for_pushes(wc))
        await asyncio.sleep(0)

        return self

    async def _process_websocket_message(self, msg: aiohttp.WSMessage):

        # Process websocket message
        self._last_update = time.time()

        if msg.type == aiohttp.WSMsgType.CLOSED:
            err_msg = "Websocket closed: {}".format(msg)
            self.log.warning(err_msg)
            await self._queue.put(StopAsyncIteration(err_msg))

        elif msg.type == aiohttp.WSMsgType.ERROR:
            err_msg = "Websocket error: {}".format(msg)
            self.log.debug(err_msg)
            await self._queue.put(StopAsyncIteration(err_msg))

        else:
            await self._process_pushbullet_message(json.loads(msg.data))

    async def _process_pushbullet_message(self, msg: dict):

        # Look for websocket message announcing new pushes
        if msg == {'type': 'tickle', 'subtype': 'push'}:

            pushes = await self.account.async_get_pushes(modified_after=self.account.most_recent_timestamp,
                                                         filter_inactive=self._filter_inactive)
            self.log.debug("Retrieved {} pushes".format(len(pushes)))

            # Update timestamp for most recent push so we only get "new" pushes
            if len(pushes) > 0 and pushes[0].get('modified', 0) > self.account.most_recent_timestamp:
                self.account.most_recent_timestamp = pushes[0]['modified']

            # Process each push
            for push in pushes:

                # Filter dismissed pushes if requested
                if self._filter_dismissed is not None and bool(push.get("dismissed")):
                    self.log.debug("Skipped push because it was dismissed: {}".format(push))
                    continue  # skip this push

                # Filter on device if requested
                if self._filter_device_nickname is not None:

                    # Does push have a target device
                    target_iden = push.get("target_device_iden")
                    if target_iden is None:
                        self.log.debug("Skipped push because it was not target device: {}".format(push))
                        continue  # skip push

                    # Does target device have the right nickname?
                    target_dev = await self.account.async_get_device(iden=target_iden)
                    if target_dev is None:
                        self.log.error("Received a target_device_iden in push that did not map to a device: {}"
                                       .format(target_iden))
                        continue  # skip this push
                    if target_dev.nickname != self._filter_device_nickname:
                        continue  # skip push - wrong device

                # Passed all filters - accept push
                self.log.debug("Adding to push queue: {}".format(push))
                await self._queue.put(push)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._ws_client.__aexit__(exc_type, exc_val, exc_tb)
        await self._ws_client.close()

    def __aiter__(self) -> AsyncIterator[dict]:
        return self

    async def __anext__(self) -> dict:
        if self._ws_client.closed:
            raise StopAsyncIteration("The websocket has closed.")

        try:
            push = await self.next_push()
        except Exception as e:
            raise StopAsyncIteration(e)

        if type(push) == StopAsyncIteration:
            raise push

        return push

    async def next_push(self, timeout: int = None) -> dict:
        if timeout is None:
            push = await self._queue.get()
            if type(push) == StopAsyncIteration:
                raise push
            return push
