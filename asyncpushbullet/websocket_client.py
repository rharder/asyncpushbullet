#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Handy class for consuming websockets as a client.

Source: https://github.com/rharder/handy

August 2018 - Initial creation
"""

import asyncio
import logging
import sys
from typing import AsyncIterator, Callable

import aiohttp  # pip install aiohttp

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
        self._provided_session: aiohttp.ClientSession = session
        self._created_session: aiohttp.ClientSession = None
        self.socket: aiohttp.ClientWebSocketResponse = None
        self._queue: asyncio.Queue = None
        self.loop: asyncio.BaseEventLoop = None
        self.log = logging.getLogger(__name__)

    @staticmethod
    def connect(url,
                on_connect: Callable = None,
                on_message: Callable = None,
                on_close: Callable = None,
                loop=None,
                **kwargs):
        """Convenience method for connecting as a websocket client using callbacks."""

        async def _run():
            client = None
            try:
                async with WebsocketClient(url=url, **kwargs) as client:

                    # Connect
                    if asyncio.iscoroutinefunction(on_connect):
                        await on_connect(client)
                    elif callable(on_connect):
                        on_connect(client)

                    # Message
                    async for msg in client:
                        if asyncio.iscoroutinefunction(on_message):
                            await on_message(client, msg)
                        elif callable(on_message):
                            on_message(client, msg)

            finally:

                # Close
                if on_close:
                    if asyncio.iscoroutinefunction(on_close):
                        await on_close(client)
                    elif callable(on_close):
                        on_close(client)

        asyncio.run_coroutine_threadsafe(_run(), loop or asyncio.get_event_loop())

    async def _create_session(self) -> aiohttp.ClientSession:

        # TCP options
        aio_connector: aiohttp.TCPConnector = None
        if self.verify_ssl is not None and self.verify_ssl is False:
            aio_connector = aiohttp.TCPConnector(ssl=False)

        # Create session
        session = aiohttp.ClientSession(headers=self.headers, connector=aio_connector)
        self.log.debug("Created session {}".format(id(session)))

        return session

    async def close(self):
        if self.socket:
            if self.socket.closed:
                self.log.debug("Socket {} already closed".format(id(self.socket)))
            else:
                await self.socket.close()
                self.log.info("Closed socket {}".format(id(self.socket)))
        if self._created_session:  # Only close session if we created it here
            if self._created_session.closed:
                self.log.debug("Session {} already closed".format(id(self._created_session)))
            else:
                await self._created_session.close()
                self.log.debug("Closed session {}".format(id(self._created_session)))

    @property
    def closed(self):
        if self.socket is None:
            raise Exception("No underlying websocket to close -- has this websocket connected yet?")
        return self.socket.closed

    async def send_str(self, data):
        """Sends a string to the websocket server."""
        await self.socket.send_str(str(data))
        await asyncio.sleep(0)

    async def send_bytes(self, data):
        """Sends raw bytes to the websocket server."""
        await self.socket.send_bytes(data)
        await asyncio.sleep(0)

    async def send_json(self, data):
        """Converts data to a json message and sends to the websocket server."""
        await self.socket.send_json(data)
        await asyncio.sleep(0)

    async def flush_incoming(self, timeout: float = None):
        """Flushes (throws away) all messages received to date but not yet consumed.

        The method will return silently if the timeout period is reached.

        :param float timeout: the optional timeout in seconds
        """

        async def _flush_all(_timeout=None):
            if timeout:  # Use await to dump anything that arrives in the timeout window
                while True:
                    _ = await self._queue.get()
                    if self.log.isEnabledFor(logging.DEBUG):
                        self.log.debug("flushed: {}".format(_))

            else:  # Else empty the queue as fast as possible without awaiting
                try:
                    while True:
                        _ = self._queue.get_nowait()
                        if self.log.isEnabledFor(logging.DEBUG):
                            self.log.debug("Flushed: {}".format(_))

                except asyncio.QueueEmpty:
                    pass

        try:
            await asyncio.wait_for(_flush_all(timeout), timeout=timeout)
        except asyncio.futures.TimeoutError:
            pass

    def flush_incoming_threadsafe(self, timeout: float = None):
        """Flushes (throws away) all messages received to date but not yet consumed.

        The method will return silently if the timeout period is reached.

        This method is threadsafe, which also means it gets scheduled on the
        appropriate thread "sometime" in the future.  Upon exiting this function,
        the queue may not yet be flushed or even have begun the flushing process.

        :param float timeout: the optional timeout in seconds
        """
        asyncio.run_coroutine_threadsafe(self.flush_incoming(timeout=timeout), self.loop)

    async def next_msg(self, timeout: float = None) -> aiohttp.WSMessage:
        """Returns the next message from the websocket server.

         This method may throw a StopAsyncIteration exception if the socket
         closes or another similar event occurs.

         If a timeout is specified, this method may throw an
         asyncio.futures.TimeoutError (not the builtin version) if the timeout
         period is exceeded without a message being available from the server.
         """
        if timeout is None:
            msg: aiohttp.WSMessage = await self._queue.get()
            if type(msg) == StopAsyncIteration:
                raise msg
            return msg
        else:
            msg: aiohttp.WSMessage = await asyncio.wait_for(self.next_msg(), timeout=timeout)
            return msg

    async def __aenter__(self):
        """
        :rtype: WebsocketClient
        """
        self.loop = asyncio.get_event_loop()
        self._queue: asyncio.Queue = asyncio.Queue()

        # Make connection
        try:
            session = self._provided_session
            if session is None:
                self._created_session = await self._create_session()
                session = self._created_session
            self.socket = await session.ws_connect(self.url, proxy=self.proxy)
            self.log.debug("Connected socket {} to {}".format(id(self.socket), self.url))
        except Exception as ex:
            if self._provided_session:
                await self._provided_session.close()
                self._provided_session = None
            raise ex

        # Set up listener to receive messages and put them in a queue
        async def _listen_for_messages():
            try:

                # Spend time here waiting for incoming messages
                msg: aiohttp.WSMessage
                async for msg in self.socket:
                    if self.log.isEnabledFor(logging.DEBUG):
                        self.log.debug("Received {}".format(msg))
                    await self._queue.put(msg)
                    await asyncio.sleep(0)

            except Exception as e:
                sai = StopAsyncIteration(e).with_traceback(sys.exc_info()[2])
                await self._queue.put(sai)
            else:
                sai = StopAsyncIteration()
                await self._queue.put(sai)

        asyncio.get_event_loop().create_task(_listen_for_messages())
        await asyncio.sleep(0)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __aiter__(self) -> AsyncIterator[aiohttp.WSMessage]:
        return WebsocketClient._Iterator(self)

    def with_timeout(self, timeout=None) -> AsyncIterator[aiohttp.WSMessage]:
        """Enables the async for loop to have a timeout.

        async for msg in client.timeout(1):
            ...
        """
        return WebsocketClient._Iterator(self, timeout=timeout)

    class _Iterator(AsyncIterator):
        def __init__(self, ws_client, timeout: float = None):
            self.timeout = timeout
            self.ws_client: WebsocketClient = ws_client

        def __aiter__(self) -> AsyncIterator[aiohttp.WSMessage]:
            return self

        async def __anext__(self) -> aiohttp.WSMessage:
            if self.ws_client.socket.closed:
                raise StopAsyncIteration("The websocket has closed.")

            return await self.ws_client.next_msg(timeout=self.timeout)
