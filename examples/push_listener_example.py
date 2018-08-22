#!/usr/bin/env python3
"""
Demonstrates how to consume new pushes in an asyncio for loop.
"""
import asyncio
import logging
import os
import pprint
import sys

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import PushListener2

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


# logging.basicConfig(level=logging.DEBUG)
# logging.getLogger("pushbullet.async_listeners").setLevel(logging.DEBUG)

def main_new_listener():
    proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")

    async def _run():
        try:
            account = AsyncPushbullet(api_key=API_KEY, proxy=proxy, verify_ssl=False)
            async with PushListener2(account) as pl2:

                async for push in pl2:
                    print("Push:", pprint.pformat(push))

        except Exception as ex:
            print("_run() exception:", ex)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    try:
        main_new_listener()
    except KeyboardInterrupt:
        print("Quitting")
        pass
