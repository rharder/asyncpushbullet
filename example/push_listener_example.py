#!/usr/bin/env python3
"""
Demonstrates how to consume new pushes in an asyncio for loop.
"""
import asyncio
from pprint import pprint
import sys
sys.path.append("..")
from pushbullet import AsyncPushbullet
from pushbullet.listeners import PushListener

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = "v1WadrAI7e0zaEefOs3dVqnXtyRxWRSuZdujzlLkPSZgq"  # YOUR API KEY
HTTP_PROXY_HOST = None
HTTP_PROXY_PORT = None


async def co_run(pb):
    async for p in PushListener(pb):
        pprint(p)


def main1():
    """ Uses the listener in an asynchronous for loop. """
    pb = AsyncPushbullet(API_KEY)

    asyncio.ensure_future(co_run(pb))

    loop = asyncio.get_event_loop()
    loop.run_forever()


async def push_received(p):
    pprint(p)
    pb = AsyncPushbullet(API_KEY)
    await pb._async_get_data("https://generate.error")


def main2():
    """ Uses a callback scheduled on an event loop"""
    pb = AsyncPushbullet(API_KEY)
    listener = PushListener(pb)
    listener.start_callbacks(push_received)

    loop = asyncio.get_event_loop()
    loop.run_forever()


if __name__ == '__main__':
    if API_KEY == "" and len(sys.argv) > 1:
        API_KEY = sys.argv[1]
    main2()