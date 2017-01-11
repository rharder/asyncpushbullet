import asyncio
import inspect
import json

import aiohttp
import time

import logging

from pushbullet import AsyncPushbullet


class WsListener(object):
    WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'
    log = logging.getLogger(__name__ + ".WsListener")

    def __init__(self, account):
        self._account = account
        self._ws = None  # type: aiohttp.ClientWebSocketResponse
        self.last_update = 0
        self._pushes = []

    def start_callbacks(self, func, loop=None):
        """
        Begins callbacks to func on the given event loop or the base event loop
        if none is provided.

        The callback function will receive one parameter, the item that was received.
        :param func: The callback function
        """
        async def _listen(func):
            async for x in self:
                if inspect.iscoroutinefunction(func):
                    await func(x)
                else:
                    func(x)
        asyncio.ensure_future(_listen(func), loop=loop)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._ws is None:
            api_key = self._account.api_key
            self._ws = await self._account._aio_session.ws_connect(self.WEBSOCKET_URL + api_key)
            WsListener.log.debug("Connected to websocket {}".format(self._ws))

        msg = await self._ws.receive()
        WsListener.log.debug("Websocket message received: {}".format(msg))

        self.last_update = time.time()
        if msg.type == aiohttp.WSMsgType.CLOSED:
            raise StopAsyncIteration("Websocket closed: {}".format(msg))
        elif msg.type == aiohttp.WSMsgType.ERROR:
            raise StopAsyncIteration("Websocket error: {}".format(msg))
        return msg


class PushListener(WsListener):
    log = logging.getLogger(__name__ + ".PushListener")

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
            PushListener.log.debug("__anext__ returning cached push ({} remaining)".format(len(self._pushes) - 1))
            return self._pushes.pop(0)
        else:
            while True:
                msg = await super().__anext__()  # Wait for tickle

                data = json.loads(msg.data)
                if msg.type == aiohttp.WSMsgType.TEXT and data == {'type': 'tickle', 'subtype': 'push'}:

                    pushes = await self._account.async_get_pushes(modified_after=self._most_recent_timestamp)
                    PushListener.log.debug("Retrieved {} pushes".format(len(pushes)))
                    if len(pushes) > 0 and pushes[0].get('modified', 0) > self._most_recent_timestamp:
                        self._most_recent_timestamp = pushes[0]['modified']

                    self._pushes += pushes
                    if len(self._pushes) > 0:
                        p = await self.__anext__()
                        return p
