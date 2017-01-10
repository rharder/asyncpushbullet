#!/usr/bin/env python3
import asyncio
from pprint import pprint

__author__ = 'Igor Maculan <n3wtron@gmail.com>'
import logging

from pushbullet import Listener
from pushbullet import AsyncPushbullet

logging.basicConfig(level=logging.DEBUG)

API_KEY = ''  # YOUR API KEY
HTTP_PROXY_HOST = None
HTTP_PROXY_PORT = None


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
