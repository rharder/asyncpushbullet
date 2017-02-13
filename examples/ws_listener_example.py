#!/usr/bin/env python3
"""
Demonstrates how to consume new pushes in an asyncio for loop.
"""
import asyncio
import sys

import logging
import threading
from functools import partial

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import WebsocketListener

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
HTTP_PROXY_HOST = None
HTTP_PROXY_PORT = None

logging.basicConfig(level=logging.DEBUG)
# logging.getLogger("pushbullet.async_listeners").setLevel(logging.DEBUG)


# ################
# Technique 1: async for ...
#

async def co_run(pb: AsyncPushbullet):
    async for ws_msg in WebsocketListener(pb):
        print("ws msg received:", ws_msg)


def main1():
    """ Uses the listener in an asynchronous for loop. """
    pb = AsyncPushbullet(API_KEY, verify_ssl=False)
    asyncio.ensure_future(co_run(pb))

    # async def _timeout():
    #     await asyncio.sleep(2)
    #     pb.close()
    # asyncio.ensure_future(_timeout())

    loop = asyncio.get_event_loop()
    loop.run_forever()


# ################
# Technique 2: Callbacks
#

async def connected(listener: WebsocketListener):
    print("Connected to websocket")
    # await listener.account.async_push_note("Connected to websocket", "Connected to websocket")


async def ws_msg_received(ws_msg, listener: WebsocketListener):
    print("ws_msg_received:", ws_msg)


def main2():
    """ Uses a callback scheduled on an event loop"""
    pb = AsyncPushbullet(API_KEY, verify_ssl=False)
    listener = WebsocketListener(pb, on_connect=connected, on_message=ws_msg_received)

    async def _timeout():
        await asyncio.sleep(2)
        print("ZZZ _timeout() listener.close()...")
        listener.close()
    asyncio.ensure_future(_timeout())

    loop = asyncio.get_event_loop()
    loop.run_forever()

#
# def main3():
#
#     async def _print(*kargs, **kwargs):
#         loop = asyncio.get_event_loop()
#         print("[loop {}]".format(id(loop)), *kargs, **kwargs)
#
#     def _run(loop):
#         asyncio.set_event_loop(loop)
#         print("starting io loop", id(loop))
#         loop.run_forever()
#
#     ioloop = asyncio.new_event_loop()
#     ioloop.create_task(_print("I am ioloop"))
#     t = threading.Thread(target=partial(_run, ioloop))
#     t.daemon = True
#     t.start()
#
#
#     pb = AsyncPushbullet(API_KEY, verify_ssl=False, loop=ioloop)
#     listener = PushListener(pb, on_connect=connected, on_message=ws_msg_received)
#
#     loop = asyncio.get_event_loop()
#     loop.create_task(_print("i am main loop"))
#     print("starting main loop", id(loop))
#     loop.run_forever()


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    try:
        # main1()
        main2()
        # main3()
    except KeyboardInterrupt:
        print("Quitting")
        pass
