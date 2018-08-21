#!/usr/bin/env python3
"""
Demonstrates how to consume new pushes in an asyncio for loop.
"""
import asyncio
import logging
import pprint
import sys
import threading
from functools import partial

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import PushListener, PushListener2

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = ""

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


# logging.basicConfig(level=logging.DEBUG)
# logging.getLogger("pushbullet.async_listeners").setLevel(logging.DEBUG)

def main_new_listener():

    async def _run():
        try:
            account = AsyncPushbullet(api_key=API_KEY, proxy=PROXY, verify_ssl=False)
            async with PushListener2(account) as pl2:
                # print("Awaiting first push...")
                # push = await pl2.next_push()
                # print("Next push:", push)

                async for push in pl2:
                    print("Push:", pprint.pformat(push))

        except Exception as ex:
            print("_run() exception:", ex)
            ex.with_traceback()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())


# ################
# Technique 1: async for ...
#

async def co_run(pb: AsyncPushbullet):
    pl = PushListener(pb, on_connect=print)

    # devs = await pb.async_get_devices()
    # # devs = pb.devices
    # print("DEVICES", devs)
    # pprint(devs)

    async def _timeout_and_close(delay: int = 5):
        await asyncio.sleep(delay)
        print("Closing... in {} seconds".format(delay))
        await pl.close()
        await pb.close()

    # asyncio.get_event_loop().create_task(_timeout_and_close())

    async for p in pl:
        print("Push received:", p)


def main1():
    """ Uses the listener in an asynchronous for loop. """

    pb = AsyncPushbullet(API_KEY, verify_ssl=False, proxy=PROXY)
    print(pb.get_new_pushes(limit=1))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(co_run(pb))


# ################
# Technique 2: Callbacks
#

async def connected(listener: PushListener):
    print("Connected to websocket")
    await listener.account.async_push_note("Connected to websocket", "Connected to websocket")


async def on_close(listener: PushListener):
    print("PushListener closed")


async def push_received(p: dict, listener: PushListener):
    print("Push received:", p)


def main2():
    """ Uses a callback scheduled on an event loop"""
    pb = AsyncPushbullet(API_KEY, verify_ssl=False, proxy=PROXY)
    listener = PushListener(pb, on_connect=connected, on_message=push_received)

    loop = asyncio.get_event_loop()
    loop.run_forever()


def main3():
    async def _print(*kargs, **kwargs):
        loop = asyncio.get_event_loop()
        print("[loop {}]".format(id(loop)), *kargs, **kwargs)

    def _run(loop):
        asyncio.set_event_loop(loop)
        print("starting io loop", id(loop))
        loop.run_forever()

    ioloop = asyncio.new_event_loop()
    ioloop.create_task(_print("I am ioloop"))
    t = threading.Thread(target=partial(_run, ioloop))
    t.daemon = True
    t.start()

    pb = AsyncPushbullet(API_KEY, verify_ssl=False, loop=ioloop, proxy=PROXY)
    listener = PushListener(pb, on_connect=connected, on_message=push_received)

    loop = asyncio.get_event_loop()
    loop.create_task(_print("i am main loop"))
    print("starting main loop", id(loop))
    loop.run_forever()


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

    try:
        main_new_listener()
        # main1()
        # main2()
        # main3()
    except KeyboardInterrupt:
        print("Quitting")
        pass
