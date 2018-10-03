#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import traceback
from asyncio import futures
from collections import namedtuple
from typing import TypeVar, Generic, AsyncIterator

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet, LiveStreamListener

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

T = TypeVar('T')


class EphemeralComm(Generic[T]):

    def __init__(self, pb: AsyncPushbullet, t: namedtuple):
        self.pb: AsyncPushbullet = pb
        self.t: namedtuple = t
        self.lsl: LiveStreamListener = None
        self.queue: asyncio.Queue = None
        self.ephemeral_type: str = f"ephemeral:{self.t.__name__}"

    @property
    def closed(self):
        return self.lsl is None or self.lsl.closed

    async def close(self):
        if self.lsl:
            await self.lsl.close()

    async def __aenter__(self):
        self.queue = asyncio.Queue()
        ready = asyncio.Event()

        async def _listen():
            try:
                async with LiveStreamListener(self.pb, types=self.ephemeral_type) as lsl:
                    self.lsl = lsl
                    ready.set()
                    async for msg in lsl:
                        del msg["push"]["type"]
                        kmsg = self.t(**msg["push"])
                        await self.queue.put(kmsg)
            except Exception as ex:
                print("ERROR:", ex, file=sys.stderr, flush=True)
                traceback.print_tb(sys.exc_info()[2])
                await self.queue.put(StopAsyncIteration(ex).with_traceback(sys.exc_info()[2]))
            else:
                await self.queue.put(StopAsyncIteration())

            # print("LiveStreamListener closed:", self.lsl.closed)

        asyncio.get_event_loop().create_task(_listen())
        await ready.wait()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.lsl and not self.lsl.closed:
            await self.lsl.close()

    def __aiter__(self) -> AsyncIterator[T]:
        # return self
        return EphemeralComm._Iterator(self, break_on_timeout=True)

    # async def __anext__(self) -> T:
    #     if self.closed:
    #         raise StopAsyncIteration()
    #     else:
    #         kmsg = await self.queue.get()
    #         if isinstance(kmsg, StopAsyncIteration):
    #             raise kmsg
    #         return kmsg

    async def next(self, timeout=None, break_on_timeout=False, timeout_val=None) -> T:
        """Returns the next message or None if the stream has closed or waiting times out."""
        aiter = EphemeralComm._Iterator(self, timeout=timeout, timeout_val=timeout_val,
                                        break_on_timeout=break_on_timeout)
        return await aiter.__anext__()
        # try:
        #     kmsg = await asyncio.wait_for(self.__anext__(), timeout=timeout)
        # # except futures.TimeoutError as te:
        # #     return None
        # except StopAsyncIteration as sai:
        #     return None
        # else:
        #     return kmsg

    async def send(self, kmsg: T):
        if self.closed:
            raise RuntimeError("Unable to send -- underlying connection is closed.")
        try:
            d = kmsg._asdict()
            d["type"] = self.t.__name__
            await self.pb.async_push_ephemeral(d)
        except Exception as ex:
            print("ERROR:", ex, file=sys.stderr, flush=True)
            traceback.print_tb(sys.exc_info()[2])

    def with_timeout(self, timeout=None, break_on_timeout=True, timeout_val=None) -> AsyncIterator[T]:
        """Enables the async for loop to have a timeout.

        async for msg in ec.timeout(1):
            if msg is None:
                ...
            else:
                ...
        """
        return EphemeralComm._Iterator(self, timeout=timeout, timeout_val=timeout_val,
                                       break_on_timeout=break_on_timeout)

    class _Iterator(AsyncIterator):
        def __init__(self, parent, timeout: float = None, timeout_val=None, break_on_timeout=True):
            self.timeout = timeout
            self.returnval = timeout_val
            self.break_on_timeout = break_on_timeout
            self.parent = parent

        def __aiter__(self) -> AsyncIterator[T]:
            return self

        async def __anext__(self) -> T:
            if self.parent.closed:
                raise StopAsyncIteration("EphemeralComm is closed.")
            else:
                try:
                    kmsg = await asyncio.wait_for(self.parent.queue.get(), timeout=self.timeout)

                except futures.TimeoutError as te:
                    if self.break_on_timeout:
                        raise StopAsyncIteration(f"Timed out after {self.timeout} seconds.") \
                            .with_traceback(sys.exc_info()[2])
                    else:
                        return None

                except futures.CancelledError as ce:
                    raise StopAsyncIteration(f"Cancelled.").with_traceback(sys.exc_info()[2])

                else:
                    if isinstance(kmsg, StopAsyncIteration):
                        raise kmsg
                    else:
                        return kmsg
