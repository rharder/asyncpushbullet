#!/usr/bin/env python3
"""
Demonstrates how to consume new pushes in an asyncio for loop.
"""
import asyncio
import os
import pprint
import sys

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import PushListener2

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
    async def _run():
        while True:
            account = AsyncPushbullet(api_key=API_KEY, proxy=PROXY, verify_ssl=False)
            try:
                print("Connectiong to Pushbullet...", end="", flush=True)
                async with PushListener2(account) as pl2:
                    print("Connected.", flush=True)

                    # Wait indefinitely for pushes
                    async for push in pl2:
                        print("Push:", pprint.pformat(push))

            except Exception as ex:
                print("_run() exception:", ex)

            print("Disconnected.  Waiting 10 seconds and trying again...")
            await asyncio.sleep(10)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    try:
        main()
    except KeyboardInterrupt:
        print("Quitting")
        pass
