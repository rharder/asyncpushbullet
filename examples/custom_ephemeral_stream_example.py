#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import traceback
from asyncio import futures
from collections import namedtuple
from typing import TypeVar, Generic, AsyncIterator

from asyncpushbullet.ephemeral_comm import EphemeralComm

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet, LiveStreamListener

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")

Msg = namedtuple("Msg", ["title", "body"], defaults=(None, None))


def main():
    q = asyncio.Queue()

    async def _listen():
        try:
            async with AsyncPushbullet(API_KEY, proxy=PROXY) as pb:
                async with EphemeralComm(pb, Msg) as ec:  # type: EphemeralComm[Msg]
                    await q.put(ec)
                    print(await ec.next(.5))
                    print(await ec.next(.5))
                    print(await ec.next(.5))
                    await ec.close()

        except Exception as ex:
            print("ERROR:", type(ex), ex, file=sys.stderr, flush=True)
            traceback.print_tb(sys.exc_info()[2])
        finally:
            print("AsyncPushbullet disconnected.", flush=True)

    async def _send_stuff():
        ec: EphemeralComm = await q.get()
        await asyncio.sleep(1)
        # msg = {"type": "mystuff"}
        # msg["what else do I want to say"] = "Just add extra keys"
        # msg = MyStuff(data={"what else do I want to say": "Just add extra keys"})
        # msg = {"type":"mystuff", "what else do I want to say": "Just add extra keys"}
        msg = Msg(title="mytitle", body="my body")
        try:
            await ec.send(msg)
        except Exception as ex:
            print("ERROR:", type(ex), ex, file=sys.stderr, flush=True)
            traceback.print_tb(sys.exc_info()[2])

    loop = asyncio.get_event_loop()
    loop.create_task(_send_stuff())
    loop.run_until_complete(_listen())


if __name__ == "__main__":
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    main()
