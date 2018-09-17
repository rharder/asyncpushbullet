#!/usr/bin/env python3
"""
Example of how to have an executable action that is straight python code
"""
import asyncio
from pprint import pprint

from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.command_line_listen import ListenApp, Action



# class MyAction(Action):

# async def on_push(push: dict, app: ListenApp):
async def on_push(push: dict, pb: AsyncPushbullet):
    await asyncio.sleep(1)
    print("title={}, body={}".format(push.get("title"), push.get("body")), flush=True)

    if push.get("body", "").strip().lower() == "a":
        # pb.log.info("{} sending a note".format(__file__))
        # pb = app.account
        p = await pb.async_push_note(title="Got an A!", body="foo")
        # await app.respond(title="my response", body="foo")
        return p