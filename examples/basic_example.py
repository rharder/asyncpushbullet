# !/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import sys

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet, InvalidKeyError, PushbulletError, PushListener

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
    async def _run():
        try:
            async with AsyncPushbullet(API_KEY, proxy=PROXY) as pb:

                # List devices
                devices = await pb.async_get_devices()
                print("Devices:")
                for dev in devices:
                    print("\t", dev)

                # Send a push
                push = await pb.async_push_note(title="Success", body="I did it!")
                print("Push sent:", push)

                # Ways to listen for pushes
                async with PushListener(pb) as pl:
                    # This will retrieve the previous push because it occurred
                    # after the enclosing AsyncPushbullet connection was made
                    push = await pl.next_push()
                    print("Previous push, now received:", push)

                    # Get pushes forever
                    print("Awaiting pushes forever...")
                    async for push in pl:
                        print("Push received:", push)



        except InvalidKeyError as ke:
            print(ke, file=sys.stderr)

        except PushbulletError as pe:
            print(pe, file=sys.stderr)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())



if __name__ == "__main__":
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    main()
