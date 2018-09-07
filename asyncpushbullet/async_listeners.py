# -*- coding: utf-8 -*-
"""
Asynchronous listeners for connecting to Pushbullet's realtime event stream.

Pushbullet's API: https://docs.pushbullet.com/#realtime-event-stream
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator, Set, Iterable

import aiohttp  # pip install aiohttp

from .async_pushbullet import AsyncPushbullet
from .errors import PushbulletError
from .websocket_client import WebsocketClient

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"


class PushListener:
    WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'

    def __init__(self, account: AsyncPushbullet,
                 ignore_inactive: bool = True,
                 ignore_dismissed: bool = True,
                 only_this_device_nickname: str = None,
                 types: Iterable[str] = ("push",)):
        """Creates a Pushlistener2 to await pushes using asyncio.

        The types parameter can be used to limit which kinds of pushes
        are returned in an async for loop or the next_push() call.
        The default is to show actual pushes only, not ephemerals.
        The possible values in the tuple at this time are only
        push, ephemeral, and ephemeral:xxx where xxx is matched to
        the "type" parameter if the ephemeral payload has that.
        For instance to listen only for the universal copy/paste
        pushes, you could pass in the tuple ("ephemeral:clip",).

        :param account: the AsyncPushbullet object that represents the account
        :param ignore_inactive: ignore inactive pushes, defaults to true
        :param ignore_dismissed:  ignore dismissed pushes, defaults to true
        :param only_this_device_nickname: only show pushes from this device
        :param types: the types of pushes to show
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.pb = account  # type: AsyncPushbullet
        self._last_update = 0  # type: float
        self._ignore_inactive = ignore_inactive  # type: bool
        self._ignore_dismissed = ignore_dismissed  # type: bool
        self._only_this_device_nickname = only_this_device_nickname  # type: str
        self._ws_client = None  # type: WebsocketClient
        self._loop = None  # type: asyncio.BaseEventLoop
        self._queue = None  # type: asyncio.Queue

        # Push types are what should be allowed through.
        # Ephemerals can be sub-typed like so: ephemeral:clip
        # The ephemeral_types variable contains the post-colon words
        self.push_types = set(types)  # type: Set[str]
        self.ephemeral_types = tuple([x.split(":")[-1] for x in self.push_types if len(x.split(":")) > 1])

    @property
    def closed(self):
        if self._ws_client is None:
            raise PushbulletError("No underlying websocket to close -- has this websocket connected yet?")
        return self._ws_client.closed

    async def close(self):
        await self._ws_client.close()

    async def __aenter__(self):
        self._queue = asyncio.Queue()

        # Are we filtering on device?
        if self._only_this_device_nickname is not None:
            device = await self.pb.async_get_device(nickname=self._only_this_device_nickname)
            if device is None:
                self.log.warning(
                    "Filtering on device name that does not yet exist: {}".format(self._only_this_device_nickname))
            del device

        # Load pushes that arrived since parent AsyncPushbullet was connected
        await self._process_pushbullet_message_tickle_push()

        async def _listen_for_websocket_messages(_wc: WebsocketClient):
            try:

                # Stay here for a while receiving messages
                async for msg in _wc:
                    await self._process_websocket_message(msg)

            except Exception as e:
                raise e
                # sai = StopAsyncIteration(e)
                # await self._queue.put(sai)
            else:
                msg = "Websocket closed" if _wc.closed else None
                sai = StopAsyncIteration(msg)
                await self._queue.put(sai)

        session = await self.pb.aio_session()
        wc = WebsocketClient(url=self.WEBSOCKET_URL + self.pb.api_key,
                             proxy=self.pb.proxy,
                             verify_ssl=self.pb.verify_ssl,
                             session=session)
        self._ws_client = await wc.__aenter__()
        asyncio.get_event_loop().create_task(_listen_for_websocket_messages(wc))
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
            self.log.debug("WebSocket message: {}".format(msg.data))
            await self._process_pushbullet_message(json.loads(msg.data))

    async def _process_pushbullet_message(self, msg: dict):

        # If everything is requested, then immediately post the message.
        # It might still require some follow-up processing though.
        if not self.push_types:
            await self._queue.put(msg)

        # Look for ephemeral messages
        # Takes special processing to sort through ephemerals.
        # Example values in self.push_types: ephemeral, ephemeral:clip
        if "type" in msg and "push" in msg:  # Ephemeral

            # If we're looking for ALL ephemerals, that's easy
            if "ephemeral" in self.push_types:
                await self._queue.put(msg)

            elif self.ephemeral_types:  # If items in the list

                # See if there is a sub-type in the ephemeral
                sub_push = msg.get("push")
                if type(sub_push) is dict:
                    sub_type = sub_push.get("type")
                    if sub_type is not None and sub_type in self.ephemeral_types:
                        await self._queue.put(msg)

        # Tickles requested or all messages requested?
        if msg.get("type") == "tickle":

            if "tickle" in self.push_types:  # All tickles have been requested
                await self._queue.put(msg)

            # If we got a push tickle, retrieve pushes
            if msg.get("subtype") == "push":
                await self._process_pushbullet_message_tickle_push()

            elif msg.get("subtype") == "device":
                self.pb._devices = None

            elif msg.get("subtype") == "chat":
                self.pb._chats = None

            elif msg.get("subtype") == "channel":
                self.pb._channels = None

        elif "type" in msg and msg["type"] in self.push_types:
            # Not sure what "type" this would be, but let's put it there
            await self._queue.put(msg)

        else:
            pass
            # raise Exception("Didn't expect any 'else' code here', msg: {}".format(msg))

    async def _process_pushbullet_message_tickle_push(self):  # , msg: dict):
        """When we received a tickle regarding a push."""
        await self.pb.async_verify_key()
        pushes = await self.pb.async_get_pushes(modified_after=self.pb.most_recent_timestamp,
                                                active_only=self._ignore_inactive)
        self.log.debug("Retrieved {} pushes".format(len(pushes)))

        # Update timestamp for most recent push so we only get "new" pushes
        if len(pushes) > 0 and pushes[0].get('modified', 0) > self.pb.most_recent_timestamp:
            self.pb.most_recent_timestamp = pushes[0]['modified']

        # Process each push
        for push in pushes:

            # Filter dismissed pushes if requested
            if self._ignore_dismissed is not None and bool(push.get("dismissed")):
                self.log.debug("Skipped push because it was dismissed: {}".format(push))
                continue  # skip this push

            # Filter on device if requested
            if self._only_this_device_nickname is not None:

                # Does push have no target at all?
                target_iden = push.get("target_device_iden")
                if target_iden is None:
                    self.log.info("Skipped push because it had no target device: {}".format(push))
                    continue  # skip push

                # Does target device not exist?
                # This would be a strange problem but could happen if
                # clients have cached devices.
                target_dev = await self.pb.async_get_device(iden=target_iden)
                if target_dev is None:
                    self.log.warning(
                        "Skipped push because the target_device_iden did not map to any known device: {}"
                            .format(push))
                    continue  # skip this push

                # Does target device have the wrong name?
                if target_dev.nickname != self._only_this_device_nickname:
                    self.log.debug("Skipped push that was not to target device {}: {}".format(
                        self._only_this_device_nickname, push
                    ))
                    continue  # skip push - wrong device

            # Passed all filters - accept push
            self.log.debug("Adding to push queue: {}".format(push))
            await self._queue.put(push)

    # async def _process_pushbullet_message_tickle_device(self, msg: dict):
    #     """When we received a tickle regarding a push."""
    #     # Just refresh the cache of devices
    #     self.pb._devices = None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._ws_client.__aexit__(exc_type, exc_val, exc_tb)
        await self._ws_client.close()

    def __aiter__(self) -> AsyncIterator[dict]:
        return PushListener._Iterator(self)

    def timeout(self, timeout=None):
        """Enables the async for loop to have a timeout.

        async for push in listener.timeout(1):
            ...
        """
        return PushListener._Iterator(self, timeout=timeout)

    async def next_push(self, timeout: float = None) -> dict:
        if timeout is None:
            push = await self._queue.get()
            if type(push) == StopAsyncIteration:
                raise push
            return push
        else:
            push = await asyncio.wait_for(self.next_push(), timeout=timeout)
            return push

    class _Iterator:
        def __init__(self, pushlistener, timeout: float = None):
            self.timeout = timeout
            self.parent = pushlistener  # type: PushListener

        def __aiter__(self) -> AsyncIterator[dict]:
            return self

        async def __anext__(self) -> dict:
            if self.parent.closed:
                raise StopAsyncIteration("The websocket has closed.")

            try:
                push = await self.parent.next_push(timeout=self.timeout)  # Wait here for another push

            except Exception as e:
                raise StopAsyncIteration(e)

            if type(push) == StopAsyncIteration:
                raise push

            return push
