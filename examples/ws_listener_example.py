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

# logging.basicConfig(level=logging.DEBUG)


# logging.getLogger("pushbullet.async_listeners").setLevel(logging.DEBUG)


# ################
# Technique 1: async for ...
#

# async def co_run(pb: AsyncPushbullet):
#     async for ws_msg in WebsocketListener(pb):  # type: dict
#         print("ws msg received:", ws_msg)


def main1():
    """ Uses the listener in an asynchronous for loop. """
    pb = AsyncPushbullet(API_KEY, verify_ssl=False)
    listener = WebsocketListener(pb)  # type: WebsocketListener
    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    async def _timeout():
        try:
            await asyncio.sleep(3)
            await listener.close()
            await pb.close()
        except Exception as e:
            print("NO BIGGIE", e)

    task = loop.create_task(_timeout())


    async def _get_pushes():
        try:
            async for ws_msg in listener:  # type: dict
                print("ws msg received:", ws_msg)
        except Exception as e:
            print("_get_pushes caught exception", e)
            raise e

    def _exc_handler(loop, context):
        print("_exc_handler", loop, context)
        # loop.run_until_complete(listener.close())

    # loop.set_exception_handler(_exc_handler)

    try:
        loop.run_until_complete(_get_pushes())
    except KeyboardInterrupt:
        print("KeyboardInterrupt")
        task.cancel()
    finally:
        print("finally...")
        loop.run_until_complete(listener.close())
        loop.run_until_complete(pb.close())
        # loop.close()


# ################
# Technique 2: Callbacks
#

async def ws_connected(listener: WebsocketListener):
    print("Connected to websocket")
    # await listener.account.async_push_note("Connected to websocket", "Connected to websocket")


async def ws_msg_received(ws_msg: dict, listener: WebsocketListener):
    print("ws_msg_received:", ws_msg)


async def ws_closed(listener: WebsocketListener):
    print("ws_closed")


def main2():
    """ Uses a callback scheduled on an event loop"""
    pb = AsyncPushbullet(API_KEY)  # , verify_ssl=False)
    listener = WebsocketListener(pb, on_connect=ws_connected,
                                 on_message=ws_msg_received,
                                 on_close=ws_closed)

    loop = asyncio.get_event_loop()
    # loop.set_debug(True)
    # async def _timeout():
    #     await asyncio.sleep(2)
    #     await listener.close()
    #     # await pb.close()
    # loop.create_task(_timeout())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("KeyboardInterrupt")
    finally:
        print("finally...")
        loop.run_until_complete(listener.close())
        loop.run_until_complete(pb.close())
        # loop.close()


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    main1()
    # main2()
