#!/usr/bin/env python3
"""
Demonstrates how to upload and push a file,
intended to be turned into a handy command line script
"""
import argparse
import asyncio
import logging
import os
import sys

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

# Exit codes
__ERR_API_KEY_NOT_GIVEN__ = 1
__ERR_INVALID_API_KEY__ = 2
__ERR_CONNECTING_TO_PB__ = 3
__ERR_FILE_NOT_FOUND__ = 4
__ERR_DEVICE_NOT_FOUND__ = 5
__ERR_NOTHING_TO_DO__ = 6
__ERR_UNKNOWN__ = 99

sys.argv += ["--key-file", "../api_key.txt"]
sys.argv += [__file__, os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.jpg")]


def main():
    args = parse_args()
    do_main(args)


def do_main(args):
    # Key
    api_key = ""
    if "PUSHBULLET_API_KEY" in os.environ:
        api_key = os.environ["PUSHBULLET_API_KEY"].strip()

    if args.key:
        api_key = args.key.strip()

    if args.key_file:
        with open(args.key_file) as f:
            api_key = f.read().strip()

    if api_key == "":
        print(
            "You must specify an API key, either at the command line or with the PUSHBULLET_API_KEY environment variable.",
            file=sys.stderr)
        sys.exit(__ERR_API_KEY_NOT_GIVEN__)

    # Verbose?
    if args.verbose:
        print("Log level: INFO")
        logging.basicConfig(level=logging.INFO)

    # Debug?
    if args.debug:
        print("Log level: DEBUG")
        logging.basicConfig(level=logging.DEBUG)

    # Proxy
    proxy = args.proxy or os.environ.get("https_proxy") or os.environ.get("http_proxy")

    exit_code = None
    pb = AsyncPushbullet(api_key, verify_ssl=False, proxy=proxy)
    loop = asyncio.get_event_loop()
    try:
        for file in args.files:  # type: str
            loop.run_until_complete(upload_file(pb, file))

    except KeyboardInterrupt as e:
        print("Caught keyboard interrupt")
    finally:
        loop.run_until_complete(pb.async_close())
        if exit_code is None:
            exit_code = 0
        sys.exit(exit_code)
        # END OF PROGRAM


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", help="Your Pushbullet.com API key")
    parser.add_argument("--key-file", help="Text file containing your Pushbullet.com API key")
    parser.add_argument("--proxy", help="Optional web proxy")
    parser.add_argument("--debug", action="store_true", help="Turn on debug logging")
    parser.add_argument("-v", "--verbose", action="store_true", help="Turn on verbose logging (INFO messages)")
    parser.add_argument('files', nargs='*')

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(__ERR_NOTHING_TO_DO__)

    return args


async def upload_file(pb: AsyncPushbullet, filename: str):

    print("Uploading to transfer.sh: {}".format(filename), flush=True)

    info = await pb.async_upload_file_to_transfer_sh(filename)  # Async via transfer.sh

    print(flush=True)

    # Push a notification of the upload "as a file":
    await pb.async_push_file(info["file_name"], info["file_url"], info["file_type"],
                             title="File: {}".format(info["file_name"]), body=None)

    await pb.async_close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Quitting")
        pass
