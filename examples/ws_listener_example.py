#!/usr/bin/env python3
"""
Demonstrates how to consume new pushes in an asyncio for loop.
"""
import asyncio
import sys

import logging
import threading
from functools import partial

from asyncpushbullet.helpers import print_function_name

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import WebsocketListener, PushListener2

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = ""

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
    pb = AsyncPushbullet(API_KEY, verify_ssl=False, proxy=PROXY)
    listener = WebsocketListener(pb)  # type: WebsocketListener
    loop = asyncio.get_event_loop()
    # loop.set_debug(True)

    def _exc_handler(loop, context):
        print("_exc_handler", loop, context)
    loop.set_exception_handler(_exc_handler)


    # Example of closing listener after a time
    async def _timeout():
        try:
            await asyncio.sleep(3)
            await listener.async_close()
            pb.close_all()
        except Exception as e:
            print("Exception. NO BIGGIE", e)
            e.with_traceback()
            raise e
        finally:
            print("Done.")
    task = loop.create_task(_timeout())


    async def _get_pushes():
        try:
            async for ws_msg in listener:  # type: dict
                print("ws msg received:", ws_msg)
        except Exception as e:
            print("_get_pushes caught exception", e)
            raise e


    try:
        loop.run_until_complete(_get_pushes())
    except KeyboardInterrupt:
        print("KeyboardInterrupt")
        task.cancel()
    except Exception as ex:
        print("Exception", ex)
    finally:
        print("finally...")
        loop.run_until_complete(listener.async_close())
        # loop.run_until_complete(pb.close())
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
        pb.close_all()
        # loop.close()


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    try:
        if PROXY == "":
            with open("../proxy.txt") as f:
                PROXY = f.read().strip()
    except Exception as e:
        pass  # No proxy file, that's OK

    main1()
    # main2()
