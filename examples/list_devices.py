#!/usr/bin/env python3
import asyncio
import os
import pprint
import sys

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY


def main():
    proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
    pb = AsyncPushbullet(API_KEY, proxy=proxy)

    async def _run():
        devices = await pb.async_get_devices()
        pprint.pprint(devices)

        await pb.async_close()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())


if __name__ == "__main__":
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    main()
