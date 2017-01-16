#!/usr/bin/env python3
"""
Demonstrates how to consume new pushes in an asyncio for loop.
"""
import asyncio
import sys
from pprint import pprint

sys.path.append("..")
from pushbullet import Pushbullet
from pushbullet import AsyncPushbullet
from pushbullet.async_listeners import PushListener

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
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
    # print(p)
    if not bool(p.get("dismissed", False)):
        print("From: {}".format(p.get("sender_name")))
        print("Title: {}".format(p.get("title")))
        print("Body: {}".format(p.get("body")))
        print()
    # pb = Pushbullet(API_KEY)
    # pb._get_data("https://generate.error")


def main2():
    """ Uses a callback scheduled on an event loop"""
    pb = AsyncPushbullet(API_KEY, verify_ssl=False)
    listener = PushListener(pb)
    listener.start_callbacks(push_received)

    loop = asyncio.get_event_loop()
    loop.run_forever()


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    try:
        main2()
    except KeyboardInterrupt:
        print("Quitting")
        pass
