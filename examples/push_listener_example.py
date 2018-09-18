#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstrates how to consume new pushes in an asyncio for loop.
"""
import asyncio
import logging
import os
import pprint
import sys

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet, oauth2
from asyncpushbullet.async_listeners import LiveStreamListener

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")

# logging.basicConfig(level=logging.DEBUG)

def main():
    async def _run():
        print("Connectiong to Pushbullet...", end="", flush=True)
        try:
            types=("push",)
            types=("tickle", "push")
            types=("nop",)
            # types=()
            async with AsyncPushbullet(api_key=API_KEY, proxy=PROXY) as pb:
                async with LiveStreamListener(pb, types=types) as lll:
                    print("Connected.", flush=True)

                    # Wait indefinitely for pushes and other notifications
                    async for item in lll:
                        print("Live stream item:", pprint.pformat(item))

        except Exception as ex:
            print("_run() exception:", ex)

        print("Disconnected.", flush=True)
        # await asyncio.sleep(10)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())


if __name__ == '__main__':
    API_KEY = oauth2.get_oauth2_key()
    if not API_KEY:
        print("Reading API key from file")
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    try:
        main()
    except KeyboardInterrupt:
        print("Quitting")
        pass
