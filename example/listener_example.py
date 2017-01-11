#!/usr/bin/env python3
import asyncio
import logging
from pprint import pprint

from pushbullet import AsyncPushbullet
from pushbullet import Listener

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

logging.basicConfig(level=logging.DEBUG)

API_KEY = ''  # YOUR API KEY
HTTP_PROXY_HOST = None
HTTP_PROXY_PORT = None
PB = None  # type: AsyncPushbullet


async def on_push(json_msg):
    pprint(json_msg)
    if json_msg == {'type': 'tickle', 'subtype': 'push'}:
        pushes = await PB.async_get_new_pushes()
        pprint(pushes)


def main():
    global PB
    PB = AsyncPushbullet(API_KEY)
    pbl = Listener(PB, on_push=on_push)
    pbl.connect()

    loop = asyncio.get_event_loop()
    loop.run_forever()


if __name__ == '__main__':
    main()
