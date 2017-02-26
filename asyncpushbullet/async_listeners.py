"""
Asynchronous listeners for connecting to Pushbullet's realtime event stream.

Pushbullet's API: https://docs.pushbullet.com/#realtime-event-stream
"""
import asyncio
import inspect
import json
import logging
import time

import aiohttp  # pip install aiohttp

from asyncpushbullet import Device
from .async_pushbullet import AsyncPushbullet
from .pushbullet import PushbulletError

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"


class WebsocketListener(object):
    WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'

    def __init__(self, account: AsyncPushbullet, on_message=None, on_connect=None,
                 on_close=None,
                 loop: asyncio.BaseEventLoop = None):
        """
        Creates a new WebsocketListener, either as a standalone object or
        as part of an "async for" construct.

        :param account: the AsyncPushbullet to connect to
        :param on_message: callback for when a new message is received
        :param on_connect: callback for when the websocket is initially connected
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        # Data
        self.account = account
        self._ws = None  # type: aiohttp.ClientWebSocketResponse
        self._last_update = 0  # type: float
        self._closed = False
        self.loop = loop or asyncio.get_event_loop()
        self._queue = None  # type: asyncio.Queue

        # Callbacks
        self._on_connect = on_connect
        self._on_close = on_close
        if on_message is not None:
            self._start_callbacks(on_message)

    async def close(self):
        """
        Disconnects from websocket and marks this listener as "closed,"
        meaning it will cease to notify callbacks or operate in an "async for"
        construct.
        """
        if self._ws is not None:
            self.log.info("Closing websocket {}".format(id(self._ws)))
            # asyncio.run_coroutine_threadsafe(self._ws.close(), self.loop)
            await self._ws.close()
            self._closed = True
            self._ws = None

    async def __aiter__(self):
        """ Called at the beginning of an "async for" construct. """
        # self.log.debug("Starting async def __aiter___() on loop {}".format(id(asyncio.get_event_loop())))

        self._queue = asyncio.Queue()

        async def _ws_loop():
            # self.log.debug("Starting async def _ws_loop() on loop {}".format(id(asyncio.get_event_loop())))

            try:
                # Connecting...
                session = await self.account.aio_session()

                async with session.ws_connect(self.WEBSOCKET_URL + self.account.api_key) as ws:
                    self._ws = ws
                    self.log.info("Connected to websocket {}".format(id(ws)))

                    # Notify callback on_connect, if registered
                    if inspect.iscoroutinefunction(self._on_connect):
                        await self._on_connect(self)
                    elif callable(self._on_connect):
                        self._on_connect(self)

                    # Get messages.  Spends most of its time here.
                    async for msg in ws:  # type: aiohttp.WSMessage
                        self.log.debug("Adding to websocket message queue: {}".format(msg))
                        await self._queue.put(msg)

                self.log.info("Websocket {} closed".format(id(ws)))

                # Notify callback of socket closed, if registered
                if inspect.iscoroutinefunction(self._on_close):
                    await self._on_close(self)
                elif callable(self._on_close):
                    self._on_close(self)
            except asyncio.TimeoutError as e:
                # self.log.warning("TimeoutError. Connection closing. {}".format(e))
                stop_msg = StopAsyncIteration("TimeoutError. Connection closing")
                self.log.warning(stop_msg)
                await self._queue.put(stop_msg)

            else:
                pass
                stop_msg = StopAsyncIteration("Connection closed")
                self.log.debug("Adding to websocket message queue: {}".format(stop_msg))
                await self._queue.put(stop_msg)


            finally:

                await self.close()
                self._closed = True
                self._ws = None

                # self.log.debug("Exiting async def _ws_loop() on loop {}".format(id(asyncio.get_event_loop())))

        loop = asyncio.get_event_loop()
        loop.create_task(_ws_loop())

        # self.log.debug("Exiting async def __aiter__() on loop {}".format(id(asyncio.get_event_loop())))
        return self

    async def __anext__(self) -> dict:
        """ Called at each iteration of an "async for" construct. """
        # self.log.debug("Starting async def __anext__() on loop {}".format(id(asyncio.get_event_loop())))

        if self._closed:
            self.log.debug("Raising StopAsyncIteration on loop {}".format(id(asyncio.get_event_loop())))
            raise StopAsyncIteration("This listener has closed.")

        self.log.debug("Awaiting websocket message queue...")
        try:
            msg = await self._queue.get()  # type: aiohttp.WSMessage
        except Exception as e:
            raise StopAsyncIteration(e)
        self.log.debug("Retrieved from websocket message queue: {}".format(msg))

        if type(msg) == StopAsyncIteration:
            raise msg
        else:
            assert type(msg) == aiohttp.WSMessage

        # Process websocket message
        self._last_update = time.time()

        if msg.type == aiohttp.WSMsgType.CLOSED:
            err_msg = "Websocket closed: {}".format(msg)
            self.log.warning(err_msg)
            self.log.debug("Raising StopAsyncIteration on loop {}".format(id(asyncio.get_event_loop())))
            raise StopAsyncIteration(err_msg)

        elif msg.type == aiohttp.WSMsgType.ERROR:
            err_msg = "Websocket error: {}".format(msg)
            self.log.debug(err_msg)
            self.log.debug("Raising StopAsyncIteration on loop {}".format(id(asyncio.get_event_loop())))
            try:
                raise StopAsyncIteration(err_msg)
            finally:
                self.close()

        else:
            # self.log.debug("Exiting async def __anext__() on loop {}".format(id(asyncio.get_event_loop())))
            return json.loads(msg.data)  # All is well - return message to async for loop

    def _start_callbacks(self, func):
        """
        Begins callbacks to func on the given event loop or the base event loop
        if none is provided.

        The callback function will receive two parameters:
            1.  the actual message being passed
            2.  "this" listener

        :param func: the callback function
        :param loop: optional event loop
        """

        async def _listen(func):
            """ Internal use only """
            # self.log.debug("Starting async def _listen() on loop {}".format(id(asyncio.get_event_loop())))

            while not self._closed:
                # try:
                async for msg in self:  # type: dict
                    if inspect.iscoroutinefunction(func):
                        await func(msg, self)
                    else:
                        func(msg, self)
                # except Exception as e:
                #     self.log.warning("Ignoring exception in callback: {}".format(e))
                #     self.log.debug("Exception caught from callback: {}".format(e), e)  # Traceback in debug mode only
                # finally:
                if not self._closed:
                    await asyncio.sleep(3)  # Throttle restarts

                    # self.log.debug("Exiting async def _listen() on loop {}".format(id(asyncio.get_event_loop())))

        asyncio.run_coroutine_threadsafe(_listen(func), loop=self.loop)


class PushListener(object):
    def __init__(self, account: AsyncPushbullet, on_message=None, on_connect=None, on_close=None,
                 filter_inactive: bool = True, filter_dismissed: bool = True,
                 filter_device_nickname: str = None):
        """
        Creates a new PushtListener, either as a standalone object or
        as part of an "async for" construct.

        :param account: the AsyncPushbullet to connect to
        :param on_message: callback for when a new message is received
        :param on_connect: callback for when the websocket is initially connected
        :param filter_inactive: default is to only include pushes that are active
        :param filter_dismissed: default is to only include pushes that are not dismissed
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.account = account
        self._most_recent_timestamp = 0.0  # type: float
        self._filter_inactive = filter_inactive
        self._filter_dismissed = filter_dismissed
        self._filter_device_nickname = filter_device_nickname
        # self._pushes = []
        self.ws_listener = None  # type: WebsocketListener

        self._closed = False
        self._queue = None  # type: asyncio.Queue

        # Callbacks
        self._on_connect = on_connect
        self._on_close = on_close
        if on_message is not None:
            self._start_callbacks(on_message)

    async def __aiter__(self):
        self._queue = asyncio.Queue()

        # Start listening to the websocket for tickles
        async def _ws_pull_pushes():
            # self.log.debug("Starting async def _ws_pull_pushes()")

            # Make sure we have a session connection and then save the current
            # "most recent timestamp" so we can track what we've pulled or not
            await self.account.aio_session()
            self._most_recent_timestamp = self.account.most_recent_timestamp

            async def _ws_on_connect(ws_listener):
                # Notify callback on_connect, if registered
                if inspect.iscoroutinefunction(self._on_connect):
                    await self._on_connect(self)
                elif callable(self._on_connect):
                    self._on_connect(self)

            self.ws_listener = WebsocketListener(self.account, on_connect=_ws_on_connect)
            async for msg in self.ws_listener:  # type: aiohttp.WSMessage

                # Look for websocket message announcing new pushes
                if msg == {'type': 'tickle', 'subtype': 'push'}:

                    pushes = await self.account.async_get_pushes(modified_after=self._most_recent_timestamp,
                                                                 filter_inactive=self._filter_inactive)
                    self.log.debug("Retrieved {} pushes".format(len(pushes)))

                    # Update timestamp for most recent push so we only get "new" pushes
                    if len(pushes) > 0 and pushes[0].get('modified', 0) > self._most_recent_timestamp:
                        self._most_recent_timestamp = pushes[0]['modified']

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
                                self.log.debug("Skipped push because it had not target device: {}".format(push))
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

            # Notify callback of socket closed, if registered
            if inspect.iscoroutinefunction(self._on_close):
                await self._on_close(self)
            elif callable(self._on_close):
                self._on_close(self)

            stop_msg = StopAsyncIteration("Websocket connection was closed")
            self.log.debug("Adding to push queue: {}".format(stop_msg))
            await self._queue.put(stop_msg)
            # self.log.debug("Exiting async def _ws_pull_pushes()")

        loop = asyncio.get_event_loop()
        loop.create_task(_ws_pull_pushes())

        return self

    async def __anext__(self) -> dict:
        if self._closed:
            raise StopAsyncIteration("This listener has closed.")

        try:
            push = await self._queue.get()
        except Exception as e:
            raise StopAsyncIteration(e)

        if type(push) == StopAsyncIteration:
            raise push
        else:
            assert type(push) == dict

        return push

    def _start_callbacks(self, func):
        """
        Begins callbacks to func on the given event loop or the base event loop
        if none is provided.

        The callback function will receive two parameters:
            1.  the actual message being passed
            2.  "this" listener

        :param func: the callback function
        :param loop: optional event loop
        """

        async def _listen(func):
            """ Internal use only """
            # self.log.debug("Starting async def _listen() on loop {}".format(id(asyncio.get_event_loop())))
            while not self._closed:
                # try:
                async for push in self:
                    if inspect.iscoroutinefunction(func):
                        await func(push, self)
                    else:
                        func(push, self)
                # except Exception as e:
                #     self.log.warning("Ignoring exception in callback: {}".format(e))
                #     self.log.debug("Exception caught from callback: {}".format(e), e)  # Traceback in debug mode only
                # finally:
                if not self._closed:
                    await asyncio.sleep(3)  # Throttle restarts
                    # self.log.debug("Exiting async def _listen()")

        asyncio.run_coroutine_threadsafe(_listen(func), loop=self.account.loop)

    async def close(self):
        """
        Disconnects from websocket and marks this listener as "closed,"
        meaning it will cease to notify callbacks or operate in an "async for"
        construct.
        """
        if self.ws_listener is not None:
            self.log.info("Closing PushListener {}".format(id(self.ws_listener)))
            # self.ws_listener.close()
            await self.ws_listener.close()
