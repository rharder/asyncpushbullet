#!/usr/bin/env python3
"""
Handy class for consuming websockets as a client.

Source: https://github.com/rharder/handy

August 2018 - Initial creation
"""

import asyncio
from typing import AsyncIterator

import aiohttp

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"
__license__ = "Public Domain"


class WebsocketClient():
    """A handy class for consuming websockets as a client.


    Source: https://github.com/rharder/handy
    Author: Robert Harder
    License: Public Domain

    """

    def __init__(self, url, headers=None, verify_ssl=None, proxy=None, session=None):
        self.url = url
        self.headers = headers
        self.verify_ssl = verify_ssl
        self.proxy = None if proxy is None or str(proxy).strip() == "" else str(proxy)
        self._session = session  # type: aiohttp.ClientSession
        self._socket = None  # type: aiohttp.ClientWebSocketResponse
        self._queue = None  # type: asyncio.Queue

    async def _create_session(self) -> aiohttp.ClientSession:
        aio_connector = None  # type: aiohttp.TCPConnector
        if self.verify_ssl is not None and self.verify_ssl is False:
            aio_connector = aiohttp.TCPConnector(ssl=False, loop=asyncio.get_event_loop())
        session = aiohttp.ClientSession(headers=self.headers, connector=aio_connector)
        return session

    async def close(self):
        await self._socket.close()
        await self._session.close()

    @property
    def closed(self):
        if self._socket is None:
            raise Exception("No underlying websocket to close -- has this websocket connected yet?")
        return self._socket.closed

    async def send_str(self, data):
        """Sends a string to the websocket server."""
        await self._socket.send_str(data)
        await asyncio.sleep(0)

    async def send_bytes(self, data):
        """Sends raw bytes to the websocket server."""
        await self._socket.send_bytes(data)
        await asyncio.sleep(0)

    async def send_json(self, data):
        """Sends a json message to the websocket server."""
        await self._socket.send_json(data)
        await asyncio.sleep(0)

    async def flush_incoming(self, timeout: float = None):
        """Flushes all messages received to date but not yet processed.

        The method will return silently if the timeout period is reached.

        :param float timeout: the timeout in seconds
        """

        async def _flush_all():
            while True:
                _ = await self._queue.get()
                await asyncio.sleep(0)

        try:
            await asyncio.wait_for(_flush_all(), timeout=timeout)
        except asyncio.futures.TimeoutError:
            pass

    async def get_msg(self, timeout: float = None) -> aiohttp.WSMessage:
        """Returns the next message from the websocket server.

         This method may throw a StopAsyncIteration exception if the socket
         closes or another similar event occurs.

         If a timeout is specified, this method may throw an
         asyncio.futures.TimeoutError (not the builtin version) if the timeout
         period is exceeded without a message being available from the server.
         """
        if timeout is None:
            msg = await self._queue.get()
            if type(msg) == StopAsyncIteration:
                raise msg
            return msg
        else:
            msg = await asyncio.wait_for(self.get_msg(), timeout=timeout)
            return msg

    async def __aenter__(self):
        self._queue = asyncio.Queue()
        self._session = self._session or await self._create_session()
        self._socket = await self._session.ws_connect(self.url, proxy=self.proxy)

        async def _listen_for_messages():
            try:

                # Spend time here waiting for incoming messages
                async for msg in self._socket:  # type: aiohttp.WSMessage
                    await self._queue.put(msg)
                    await asyncio.sleep(0)

            except Exception as e:
                sai = StopAsyncIteration(e)
                await self._queue.put(sai)
            else:
                sai = StopAsyncIteration()
                await self._queue.put(sai)

        asyncio.get_event_loop().create_task(_listen_for_messages())
        await asyncio.sleep(0)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._session.close()

    def __aiter__(self) -> AsyncIterator[aiohttp.WSMessage]:
        return WebsocketClient._Iterator(self)

    def timeout(self, timeout=None):
        """Enables the async for loop to have a timeout.

        async for msg in client.timeout(1):
            ...
        """
        return WebsocketClient._Iterator(self, timeout=timeout)

    class _Iterator:
        def __init__(self, ws_client, timeout: float = None):
            self.timeout = timeout
            self.ws_client = ws_client  # type: WebsocketClient

        def __aiter__(self) -> AsyncIterator[aiohttp.WSMessage]:
            return self

        async def __anext__(self) -> aiohttp.WSMessage:
            if self.ws_client._socket.closed:
                raise StopAsyncIteration("The websocket has closed.")

            return await self.ws_client.get_msg(timeout=self.timeout)
