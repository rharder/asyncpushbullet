# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A basic, complete example of using AsyncPushbullet to interact with the Pushbullet.com service.
"""
import asyncio
import os
import sys
import traceback

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet, InvalidKeyError, PushbulletError, LiveStreamListener

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")
EXIT_INVALID_KEY = 1
EXIT_PUSHBULLET_ERROR = 2
EXIT_OTHER = 3


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
                async with LiveStreamListener(pb) as pl:
                    # This will retrieve the previous push because it occurred
                    # after the enclosing AsyncPushbullet connection was made
                    push = await pl.next_push()
                    print("Previous push, now received:", push)

                    # Alternately get pushes with a 3 second inter-push timeout
                    print("Awaiting pushes with 3 second inter-push timeout...")
                    async for push in pl.with_timeout(3):
                        print("Push received:", push)

                    # Alternately get pushes forever
                    print("Awaiting pushes forever...")
                    async for push in pl:
                        print("Push received:", push)

        except InvalidKeyError as ke:
            print(ke, file=sys.stderr)
            return EXIT_INVALID_KEY

        except PushbulletError as pe:
            print(pe, file=sys.stderr)
            return EXIT_PUSHBULLET_ERROR

        except Exception as ex:
            print(ex, file=sys.stderr)
            traceback.print_tb(sys.exc_info()[2])
            return EXIT_OTHER

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_run())


if __name__ == "__main__":
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    sys.exit(main())
