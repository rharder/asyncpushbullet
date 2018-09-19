#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import traceback

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
    # pb = AsyncPushbullet(API_KEY, proxy=PROXY)

    msg = {"foo": "bar", 42: "23", "type": "synchronous_example"}
    # pb.push_ephemeral(msg)  # Synchronous IO

    async def _run():
        try:
            async with AsyncPushbullet(API_KEY, proxy=PROXY) as pb:
                msg["type"] = "asynchronous_example"
                await pb.async_push_ephemeral(msg)  # Asynchronous IO

                # await pb.async_close()
        except Exception as ex:
            print("ERROR:", ex, file=sys.stderr, flush=True)
            traceback.print_tb(sys.exc_info()[2])

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())


if __name__ == "__main__":
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    main()
