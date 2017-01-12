import asyncio
import inspect
import json
import logging
import time

import aiohttp

from pushbullet import AsyncPushbullet
from pushbullet import PushbulletError

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

# https://docs.pushbullet.com/#realtime-event-stream

class WsListener(object):
    """ Listens for lowest level messages coming from the Pushbullet websocket. """
    WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'

    def __init__(self, account):
        self._account = account
        self._ws = None  # type: aiohttp.ClientWebSocketResponse
        self.last_update = 0
        self._pushes = []
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

    def start_callbacks(self, func, loop=None):
        """
        Begins callbacks to func on the given event loop or the base event loop
        if none is provided.

        The callback function will receive one parameter, the item that was received.
        :param func: The callback function
        """

        async def _listen(func):
            """ Internal use only """
            while True:
                try:
                    async for x in self:
                        if inspect.iscoroutinefunction(func):
                            await func(x)
                        else:
                            func(x)
                except Exception as e:
                    self.log.warning("Ignoring exception in callback and continuing to listen...", e)
                finally:
                    await asyncio.sleep(1)  # Throttle control

        asyncio.ensure_future(_listen(func), loop=loop)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._ws is None or self._ws.closed:
            self._ws = None
            try:
                api_key = self._account.api_key
                self._ws = await self._account._aio_session.ws_connect(self.WEBSOCKET_URL + api_key)  # type: aiohttp.ClientWebSocketResponse
                self.log.debug("Connected to websocket {}".format(self._ws))
            except PushbulletError as pe:
                self.log.error("Could not connect to websocket.", pe)
                raise StopAsyncIteration(pe)

        try:
            msg = await self._ws.receive()
        except Exception as e:
            err_msg = "An error occurred while waiting on websocket messages: {}".format(e)
            self.log.error(err_msg, e)
            raise StopAsyncIteration(e)
        self.log.debug("Websocket message received: {}".format(msg))

        self.last_update = time.time()
        if msg.type == aiohttp.WSMsgType.CLOSED:
            err_msg = "Websocket closed: {}".format(msg)
            self.log.warning(err_msg)
            raise StopAsyncIteration(err_msg)
        elif msg.type == aiohttp.WSMsgType.ERROR:
            err_msg = "Websocket error: {}".format(msg)
            self.log.debug(err_msg)
            raise StopAsyncIteration(err_msg)
        return msg


class PushListener(WsListener):
    def __init__(self, account: AsyncPushbullet, filter_inactive=True):
        WsListener.__init__(self, account)
        self._super_iter = None
        self._most_recent_timestamp = account._most_recent_timestamp
        self._filter_inactive = filter_inactive

    def __aiter__(self):
        self._super_iter = super().__aiter__()
        return self

    async def __anext__(self):
        if len(self._pushes) > 0:
            self.log.debug("__anext__ returning cached push ({} remaining)".format(len(self._pushes) - 1))
            return self._pushes.pop(0)
        else:
            while True:
                msg = await super().__anext__()  # Wait for tickle

                data = json.loads(msg.data)
                if msg.type == aiohttp.WSMsgType.TEXT and data == {'type': 'tickle', 'subtype': 'push'}:

                    pushes = await self._account.async_get_pushes(modified_after=self._most_recent_timestamp)
                    self.log.debug("Retrieved {} pushes".format(len(pushes)))
                    if len(pushes) > 0 and pushes[0].get('modified', 0) > self._most_recent_timestamp:
                        self._most_recent_timestamp = pushes[0]['modified']

                    self._pushes += pushes
                    if len(self._pushes) > 0:
                        p = await self.__anext__()
                        return p
