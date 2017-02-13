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
            self.log.info("Closing websocket {}".format(self._ws))
            try:
                self._ws.close()
            except Exception as e:
                err_msg = "An error occurred while closing the websocket: {}".format(e)
                self.log.warning(err_msg)
                self.log.debug(err_msg, e)  # Traceback in debug mode only
        self._ws = None
        self._closed = True

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

        asyncio.run_coroutine_threadsafe(_listen(func), loop=self.loop)

    def __aiter__(self):
        """ Called at the beginning of an "async for" construct. """
        self.close()
        self._closed = False  # Reset the websocket
        return self

    async def __anext__(self) -> aiohttp.WSMessage:
        """ Called at each iteration of an "async for" construct. """
        if self._closed:
            raise StopAsyncIteration("This listener has closed.")

        # Lazily connect to websocket
        if self._ws is None or self._ws.closed:
            self._ws = None
            try:
                # Connecting...
                self.log.info("Connecting to websocket...")
                session = await self.account.aio_session()
                self._ws = await session.ws_connect(self.WEBSOCKET_URL + self.account.api_key)
                self.log.info("Connected to websocket {}".format(self._ws))

                # Notify callback, if registered
                if inspect.iscoroutinefunction(self._on_connect):
                    await self._on_connect(self)
                elif callable(self._on_connect):
                    self._on_connect(self)

            except PushbulletError as pe:
                self.log.error("Could not connect to websocket.", pe)
                self.close()
                raise StopAsyncIteration(pe)

        try:
            # Wait for websocket message
            msg = await self._ws.receive()

        except Exception as e:
            err_msg = "An error occurred while waiting on websocket messages: {}".format(e)
            self.log.error(err_msg, e)
            self.close()
            raise StopAsyncIteration(e)

        # Process websocket message
        self.log.debug("Websocket message received: {}".format(msg))
        self._last_update = time.time()

        if msg.type == aiohttp.WSMsgType.CLOSED:
            err_msg = "Websocket closed: {}".format(msg)
            self.log.warning(err_msg)
            raise StopAsyncIteration(err_msg)

        elif msg.type == aiohttp.WSMsgType.ERROR:
            err_msg = "Websocket error: {}".format(msg)
            self.log.debug(err_msg)
            raise StopAsyncIteration(err_msg)

        else:
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
        self._most_recent_timestamp = account._most_recent_timestamp
        self._filter_inactive = filter_inactive
        self._filter_dismissed = filter_dismissed
        self._pushes = []
        self.ws_listener = None  # type: WebsocketListener

        self._closed = False

        # Callbacks
        self._on_connect = on_connect
        if on_message is not None:
            self._start_callbacks(on_message)

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._closed:
            raise StopAsyncIteration("This listener has closed.")

        if len(self._pushes) > 0:
            self.log.debug("__anext__ returning cached push ({} remaining)".format(len(self._pushes) - 1))
            return self._pushes.pop(0)
        # TODO: LEFT OFF HERE: ws_listener created too frequently because of recursion
        else:
            while not self._closed:
                self.ws_listener = WebsocketListener(self.account, on_connect=self._on_connect)
                # Get tickle from websocket
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
                                self._pushes.append(push)

                        if len(self._pushes) > 0:
                            p = await self.__anext__()
                            return p

        self.close()
        raise StopAsyncIteration()  # Async for loop is done

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
                print("ZZZ finally")
                if not self._closed:
                    await asyncio.sleep(3)  # Throttle restarts

        asyncio.run_coroutine_threadsafe(_listen(func), loop=self.account.loop)

    def close(self):
        """
        Disconnects from websocket and marks this listener as "closed,"
        meaning it will cease to notify callbacks or operate in an "async for"
        construct.
        """
        if self.ws_listener is not None:
            self.log.info("Closing websocket {}".format(self.ws_listener))
            self.ws_listener.close()

        self.ws_listener = None
        self._closed = True

#
# class PushListener_orig(WebsocketListener):
#     """
#     Class for listening for new pushes (not ephemerals) announced over a websocket,
#     either with callbacks or in an "async for" construct.
#
#     This class listens for the websocket to send a "tickle" about new pushes, and then
#     it retrieves pushes that are new since the most recent modification date that it
#     has on record.
#
#     By default PushListener will only pass on pushes that are active and not dismissed.
#
#     Example 1:
#         async def something_happening(self):
#             async for push in PushListener(self.async_pushbullet):
#                 print("New push:", push)
#
#     Example 2:
#         def something_happening(self):
#             listener = PushListener(self.async_pushbullet,
#                                     on_connect=self.connected,
#                                     on_message=self.push_received)
#
#         def connected(self, listener):
#             print("Websocket connected.")
#
#         def push_received(self, push, async_pushbullet):
#             print("Push receveived:", push)
#     """
#
#     def __init__(self, account: AsyncPushbullet, on_message=None, on_connect=None,
#                  filter_inactive: bool = True, filter_dismissed: bool = True,
#                  loop: asyncio.BaseEventLoop = None):
#         """
#         Creates a new PushtListener, either as a standalone object or
#         as part of an "async for" construct.
#
#         :param account: the AsyncPushbullet to connect to
#         :param on_message: callback for when a new message is received
#         :param on_connect: callback for when the websocket is initially connected
#         :param filter_inactive: default is to only include pushes that are active
#         :param filter_dismissed: default is to only include pushes that are not dismissed
#         """
#         super().__init__(account, on_message=on_message, on_connect=on_connect, loop=loop)
#         self._super_iter = None  # type: WebsocketListener
#         self._most_recent_timestamp = account._most_recent_timestamp
#         self._filter_inactive = filter_inactive
#         self._filter_dismissed = filter_dismissed
#
#     def __aiter__(self):
#         self._super_iter = super().__aiter__()
#         return self
#
#     async def __anext__(self) -> dict:
#         if self._closed:
#             raise StopAsyncIteration("This listener has closed.")
#
#         if len(self._pushes) > 0:
#             self.log.debug("__anext__ returning cached push ({} remaining)".format(len(self._pushes) - 1))
#             return self._pushes.pop(0)
#
#         else:
#             while not self._closed:
#
#                 # Wait for websocket tickle
#                 msg = await super().__anext__()
#
#                 # Look for websocket message announcing new pushes
#                 data = json.loads(msg.data)
#                 if msg.type == aiohttp.WSMsgType.TEXT and data == {'type': 'tickle', 'subtype': 'push'}:
#
#                     pushes = await self.account.async_get_pushes(modified_after=self._most_recent_timestamp,
#                                                                  filter_inactive=self._filter_inactive)
#                     self.log.debug("Retrieved {} pushes".format(len(pushes)))
#
#                     # Update timestamp for most recent push so we only get "new" pushes
#                     if len(pushes) > 0 and pushes[0].get('modified', 0) > self._most_recent_timestamp:
#                         self._most_recent_timestamp = pushes[0]['modified']
#
#                     # Filter dismissed pushes if requested
#                     for push in pushes:
#                         if not self._filter_dismissed or not bool(push.get("dismissed")):
#                             self._pushes.append(push)
#
#                     if len(self._pushes) > 0:
#                         p = await self.__anext__()
#                         return p
#
#         self.close()
#         raise StopAsyncIteration()  # Async for loop is done
