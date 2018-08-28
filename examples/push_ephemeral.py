#!/usr/bin/env python3
import asyncio
import os
import sys

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
    pb = AsyncPushbullet(API_KEY, proxy=PROXY, verify_ssl=False)

    msg = {"foo": "bar", 42: "23"}
    msg["type"] = "synchronous"
    pb.push_ephemeral(msg)  # Synchronous IO

    async def _run():
        msg["type"] = "asynchronous"
        await pb.async_push_ephemeral(msg)  # Asynchronous IO

        await pb.async_close()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())


if __name__ == "__main__":
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    main()
