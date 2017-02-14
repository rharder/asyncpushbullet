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

from .async_pushbullet import AsyncPushbullet
from .pushbullet import PushbulletError

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"


class WebsocketListener(object):
    WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'

    def __init__(self, account: AsyncPushbullet, on_message=None, on_connect=None, loop: asyncio.BaseEventLoop = None):
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
        if on_message is not None:
            self._start_callbacks(on_message)

    def close(self):
        """
        Disconnects from websocket and marks this listener as "closed,"
        meaning it will cease to notify callbacks or operate in an "async for"
        construct.
        """
        if self._ws is not None:
            self.log.info("Closing websocket {}".format(id(self._ws)))

            async def _close():
                await self._ws.close()
                # self._ws = None
                # self._closed = True
                self.log.info("Closed websocket {}".format(id(self._ws)))

            asyncio.run_coroutine_threadsafe(_close(), self.loop)

    async def __aiter__(self):
        """ Called at the beginning of an "async for" construct. """
        # self.close()
        # self._closed = False  # Reset the websocket
        self.log.debug("Starting async def __aiter___() on loop {}".format(id(asyncio.get_event_loop())))

        self._queue = asyncio.Queue()

        async def _ws_loop():
            self.log.debug("Starting async def _ws_loop() on loop {}".format(id(asyncio.get_event_loop())))

            # Connecting...
            session = await self.account.aio_session()

            async with session.ws_connect(self.WEBSOCKET_URL + self.account.api_key) as ws:
                self._ws = ws
                self.log.info("Connected to websocket {}".format(id(self._ws)))

                # Notify callback, if registered
                if inspect.iscoroutinefunction(self._on_connect):
                    await self._on_connect(self)
                elif callable(self._on_connect):
                    self._on_connect(self)

                async for msg in ws:
                    await self._queue.put(msg)

            self._closed = True
            self._ws = None
            self._queue.put(StopAsyncIteration("Connection closed"))
            self.log.debug("ZZZ Exiting async def _ws_loop() on loop {}".format(id(asyncio.get_event_loop())))

        loop = asyncio.get_event_loop()
        loop.create_task(_ws_loop())

        self.log.debug("Exiting async def __aiter__() on loop {}".format(id(asyncio.get_event_loop())))
        return self

    async def __anext__(self) -> aiohttp.WSMessage:
        """ Called at each iteration of an "async for" construct. """
        self.log.debug("Starting async def __anext__() on loop {}".format(id(asyncio.get_event_loop())))

        if self._closed:
            self.log.debug("Raising StopAsyncIteration on loop {}".format(id(asyncio.get_event_loop())))
            raise StopAsyncIteration("This listener has closed.")

        msg = await self._queue.get()  # type: aiohttp.WSMessage

        if type(msg) is StopAsyncIteration:
            raise msg

        # Process websocket message
        self.log.debug("Websocket message received: {}".format(msg))
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
            raise StopAsyncIteration(err_msg)

        else:
            self.log.debug("Exiting async def __anext__() on loop {}".format(id(asyncio.get_event_loop())))
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
            self.log.debug("Starting async def _listen() on loop {}".format(id(asyncio.get_event_loop())))

            while not self._closed:
                try:
                    async for msg in self:  # type: dict
                        if inspect.iscoroutinefunction(func):
                            await func(msg, self)
                        else:
                            func(msg, self)
                except Exception as e:
                    self.log.warning("Ignoring exception in callback: {}".format(e))
                    self.log.debug("Exception caught from callback: {}".format(e), e)  # Traceback in debug mode only
                finally:
                    if not self._closed:
                        await asyncio.sleep(3)  # Throttle restarts

            self.log.debug("Exiting async def _listen() on loop {}".format(id(asyncio.get_event_loop())))

        asyncio.run_coroutine_threadsafe(_listen(func), loop=self.loop)


class WebsocketListener2(object):
    """
    Listens for lowest level messages coming from the Pushbullet websocket,
    either with callbacks or in an "async for" construct.

    This class listens for the websocket to send a message and then passes that
    message on through a callback or the "async for" construct.  The messages
    are of type aiohttp.WSMessage.

    Example 1:
        async def something_happening(self):
            async for msg in WebsocketListener(self.async_pushbullet):
                print("New message:", msg)

    Example 2:
        def something_happening(self):
            listener = WebsocketListener(self.async_pushbullet,
                                         on_connect=self.connected,
                                         on_message=self.message_received)

        def connected(self, listener: WebsocketListener):
            print("Websocket connected.")

        def message_received(self, msg: aiohttp.WSMessage, async_pushbullet: AsyncPushbullet):
            print("Message receveived:", msg)
    """

    WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'

    def __init__(self, account: AsyncPushbullet, on_message=None, on_connect=None, loop: asyncio.BaseEventLoop = None):
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
        self._last_update = 0
        # self._pushes = []
        self._closed = False
        self.loop = loop or asyncio.get_event_loop()
        self._queue = None  # type: asyncio.Queue

        # Callbacks
        self._on_connect = on_connect
        if on_message is not None:
            self._start_callbacks(on_message)

    def close(self):
        """
        Disconnects from websocket and marks this listener as "closed,"
        meaning it will cease to notify callbacks or operate in an "async for"
        construct.
        """
        if self._ws is not None:
            self.log.info("Closing websocket {}".format(id(self._ws)))

            async def _close():
                await self._ws.close()
                self._ws = None
                self._closed = True
                self.log.info("Closed websocket {}".format(id(self._ws)))

            asyncio.run_coroutine_threadsafe(_close(), self.loop)

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
            self.log.debug("Starting async def _listen() on loop {}".format(id(asyncio.get_event_loop())))

            while not self._closed:
                try:
                    async for ws_msg in self:
                        if inspect.iscoroutinefunction(func):
                            await func(ws_msg, self)
                        else:
                            func(ws_msg, self)
                except Exception as e:
                    self.log.warning("Ignoring exception in callback: {}".format(e))
                    self.log.debug("Exception caught from callback: {}".format(e), e)  # Traceback in debug mode only
                finally:
                    if not self._closed:
                        await asyncio.sleep(3)  # Throttle restarts

            self.log.debug("Exiting async def _listen() on loop {}".format(id(asyncio.get_event_loop())))

        asyncio.run_coroutine_threadsafe(_listen(func), loop=self.loop)

    async def __aiter__(self):
        """ Called at the beginning of an "async for" construct. """
        # self.close()
        # self._closed = False  # Reset the websocket
        self.log.debug("Starting async def __aiter___() on loop {}".format(id(asyncio.get_event_loop())))

        self._queue = asyncio.Queue()

        async def _ws_loop():
            self.log.debug("Starting async def _ws_loop() on loop {}".format(id(asyncio.get_event_loop())))

            # Connecting...
            session = await self.account.aio_session()

            async with session.ws_connect(self.WEBSOCKET_URL + self.account.api_key) as ws:
                self._ws = ws
                self.log.info("Connected to websocket {}".format(id(self._ws)))

                # Notify callback, if registered
                if inspect.iscoroutinefunction(self._on_connect):
                    await self._on_connect(self)
                elif callable(self._on_connect):
                    self._on_connect(self)

                async for msg in ws:
                    await self._queue.put(msg)

            self.log.debug("ZZZ Exiting async def _ws_loop() on loop {}".format(id(asyncio.get_event_loop())))
            self._queue.task_done()
            self.log.debug("ZZZ EXECUTED self._queue.task_done()")

        loop = asyncio.get_event_loop()
        loop.create_task(_ws_loop())

        self.log.debug("Exiting async def __aiter__() on loop {}".format(id(asyncio.get_event_loop())))
        return self

    async def __anext__(self) -> aiohttp.WSMessage:
        """ Called at each iteration of an "async for" construct. """
        self.log.debug("Starting async def __anext__() on loop {}".format(id(asyncio.get_event_loop())))

        if self._closed:
            self.log.debug("Raising StopAsyncIteration on loop {}".format(id(asyncio.get_event_loop())))
            raise StopAsyncIteration("This listener has closed.")

        msg = await self._queue.get()

        # Process websocket message
        self.log.debug("Websocket message received: {}".format(msg))
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
            raise StopAsyncIteration(err_msg)

        else:
            self.log.debug("Exiting async def __anext__() on loop {}".format(id(asyncio.get_event_loop())))
            return msg  # All is well - return message to async for loop


class PushListener(object):
    """
    Class for listening for new pushes (not ephemerals) announced over a websocket,
    either with callbacks or in an "async for" construct.

    This class listens for the websocket to send a "tickle" about new pushes, and then
    it retrieves pushes that are new since the most recent modification date that it
    has on record.

    By default PushListener will only pass on pushes that are active and not dismissed.

    Example 1:
        async def something_happening(self):
            async for push in PushListener(self.async_pushbullet):
                print("New push:", push)

    Example 2:
        def something_happening(self):
            listener = PushListener(self.async_pushbullet,
                                    on_connect=self.connected,
                                    on_message=self.push_received)

        def connected(self, listener):
            print("Websocket connected.")

        def push_received(self, push, async_pushbullet):
            print("Push receveived:", push)
    """

    def __init__(self, account: AsyncPushbullet, on_message=None, on_connect=None,
                 filter_inactive: bool = True, filter_dismissed: bool = True):
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
        self._pushes = []
        self.ws_listener = None  # type: WebsocketListener

        self._closed = False
        self._queue = None  # type: asyncio.Queue

        # Callbacks
        self._on_connect = on_connect
        if on_message is not None:
            self._start_callbacks(on_message)

    async def __aiter__(self):
        self._queue = asyncio.Queue()

        # Start listening to the websocket for tickles
        async def _ws_pull_pushes():
            self.log.debug("Starting async def _ws_pull_pushes()")

            # Make sure we have a session connection and then save the current
            # "most recent timestamp" so we can track what we've pulled or not
            await self.account.aio_session()
            self._most_recent_timestamp = self.account.most_recent_timestamp

            self.ws_listener = WebsocketListener(self.account, on_connect=self._on_connect)
            async for ws_msg in self.ws_listener:  # type: aiohttp.WSMessage

                # Look for websocket message announcing new pushes
                data = json.loads(ws_msg.data)
                if ws_msg.type == aiohttp.WSMsgType.TEXT and data == {'type': 'tickle', 'subtype': 'push'}:

                    pushes = await self.account.async_get_pushes(modified_after=self._most_recent_timestamp,
                                                                 filter_inactive=self._filter_inactive)
                    self.log.debug("Retrieved {} pushes".format(len(pushes)))

                    # Update timestamp for most recent push so we only get "new" pushes
                    if len(pushes) > 0 and pushes[0].get('modified', 0) > self._most_recent_timestamp:
                        self._most_recent_timestamp = pushes[0]['modified']

                    # Filter dismissed pushes if requested
                    for push in pushes:
                        if not self._filter_dismissed or not bool(push.get("dismissed")):
                            await self._queue.put(push)

            self.log.debug("Exiting async def _ws_pull_pushes()")

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
            self.log.debug("Starting async def _listen() on loop {}".format(id(asyncio.get_event_loop())))
            while not self._closed:
                try:
                    async for push in self:
                        if inspect.iscoroutinefunction(func):
                            await func(push, self)
                        else:
                            func(push, self)
                except Exception as e:
                    self.log.warning("Ignoring exception in callback: {}".format(e))
                    self.log.debug("Exception caught from callback: {}".format(e), e)  # Traceback in debug mode only
                finally:
                    if not self._closed:
                        await asyncio.sleep(3)  # Throttle restarts
            self.log.debug("Exiting async def _listen()")

        asyncio.run_coroutine_threadsafe(_listen(func), loop=self.account.loop)

    def close(self):
        """
        Disconnects from websocket and marks this listener as "closed,"
        meaning it will cease to notify callbacks or operate in an "async for"
        construct.
        """
        if self.ws_listener is not None:
            self.log.info("Closing websocket {}".format(id(self.ws_listener)))
            self.ws_listener.close()
            self.log.info("Closed websocket {}".format(id(self.ws_listener)))

        self.ws_listener = None
        self._closed = True
