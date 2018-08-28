#!/usr/bin/env python3
"""
Demonstrates how to upload and push a file.
"""
import asyncio
import os
import sys

import logging

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
    """ Uses a callback scheduled on an event loop"""

    pb = AsyncPushbullet(API_KEY, verify_ssl=False, proxy=PROXY)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(upload_file(pb, __file__))  # Upload this source code file as an example


async def upload_file(pb: AsyncPushbullet, filename: str):

    # This is the actual upload command
    # info = await pb.async_upload_file(filename)
    # info = await pb.async_upload_file_to_transfer_sh(filename)
    info = pb.upload_file_to_transfer_sh(filename)

    # Push a notification of the upload "as a file":
    await pb.async_push_file(info["file_name"], info["file_url"], info["file_type"],
                             title="File Arrived!", body="Please enjoy your file")

    # Also push a notification of the upload "as a link":
    await pb.async_push_link("Link to File Arrived!", info["file_url"], body="Please enjoy your file")

    await pb.async_close()


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    try:
        main()
    except KeyboardInterrupt:
        print("Quitting")
        pass
