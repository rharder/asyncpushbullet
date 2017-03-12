#!/usr/bin/env python3
"""
A command line script for sending pushes.

usage: push.py [-h] [-k KEY] [--key-file KEY_FILE] [-t TITLE] [-b BODY]
               [-d DEVICE] [-u URL] [-f FILE] [--transfer.sh] [--list-devices]
               [-q]

optional arguments:
  -h, --help            show this help message and exit
  -k KEY, --key KEY     Your Pushbullet.com API key
  --key-file KEY_FILE   Text file containing your Pushbullet.com API key
  -t TITLE, --title TITLE
                        Title of your push
  -b BODY, --body BODY  Body of your push (- means read from stdin)
  -d DEVICE, --device DEVICE
                        Destination device nickname
  -u URL, --url URL     URL of link being pushed
  -f FILE, --file FILE  Pathname to file to push
  --transfer.sh         Use transfer.sh website for uploading files (use with
                        --file)
  --list-devices        List registered device names
  -q, --quiet           Suppress all output

"""
import argparse
import asyncio
import contextlib
import inspect
import io
import os
import sys
import time

import aiohttp
from tqdm import tqdm

from asyncpushbullet.tqio import tqio

sys.path.append("..")  # To help when running examples direct from the source repository
from asyncpushbullet.filetype import get_file_type
from asyncpushbullet import PushbulletError
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet import Device
from asyncpushbullet import InvalidKeyError

# Exit codes
__ERR_API_KEY_NOT_GIVEN__ = 1
__ERR_INVALID_API_KEY__ = 2
__ERR_CONNECTING_TO_PB__ = 3
__ERR_FILE_NOT_FOUND__ = 4
__ERR_DEVICE_NOT_FOUND__ = 5
__ERR_NOTHING_TO_DO__ = 6

# logging.basicConfig(logging.ERROR)

# sys.argv.append("--help")
# sys.argv.append("--list-devices")
# sys.argv += ["-t", "test to device", "--device", "netmem"]
# sys.argv += ["--file", __file__]
# sys.argv += ["--file", "/Users/rob/Movies/Braveheart.mp4"]
# sys.argv.append("--transfer.sh")
# sys.argv += ["--device", "netmem"]


# sys.argv += ["-t", "foo"]
# sys.argv += ["--key-file", "../api_key.txt"]
# sys.argv += ["--key", "badkey"]

# sys.argv.append("--quiet")

def main():
    args = parse_args()
    do_main(args)


def do_main(args):
    # global API_KEY

    # Key
    api_key = ""
    if "PUSHBULLET_API_KEY" in os.environ:
        api_key = os.environ["PUSHBULLET_API_KEY"].strip()

    if args.key:
        api_key = args.key.strip()

    if args.key_file:
        with open(args.key_file) as f:
            api_key = f.read().strip()
        print("Read API key from file {}".format(args.key_file))

    if api_key == "":
        print(
            "You must specify an API key, either at the command line or with the PUSHBULLET_API_KEY environment variable.",
            file=sys.stderr)
        sys.exit(__ERR_API_KEY_NOT_GIVEN__)

    # Make connection
    pb = None  # type: AsyncPushbullet
    loop = asyncio.get_event_loop()
    try:
        pb = AsyncPushbullet(api_key)
        # pb.verify_key()
        loop.run_until_complete(pb.async_verify_key())
    except InvalidKeyError as exc:
        print(exc, file=sys.stderr)
        loop.run_until_complete(pb.close())
        sys.exit(__ERR_INVALID_API_KEY__)
    except PushbulletError as exc:
        print(exc, file=sys.stderr)
        loop.run_until_complete(pb.close())
        sys.exit(__ERR_CONNECTING_TO_PB__)

    # List devices?
    if args.list_devices:
        print("Devices:")
        for dev in pb.devices:
            print("\t", dev.nickname)
        loop.run_until_complete(pb.close())
        loop.close()
        sys.exit(0)

    # Transfer file?
    elif args.file:
        if not os.path.isfile(args.file):
            print("File not found:", args.file, file=sys.stderr)
            sys.exit(__ERR_FILE_NOT_FOUND__)

        dev = None  # type: Device
        if args.device:
            dev = loop.run_until_complete(pb.async_get_device(nickname=args.device))
            # dev = pb.get_device(nickname=args.device)
            # print("DEVICE", dev)
            if dev is None:
                print("Device not found:", args.device, file=sys.stderr)
                sys.exit(__ERR_DEVICE_NOT_FOUND__)

        file_name = os.path.basename(args.file)  # type: str
        file_url = None  # type: str
        file_type = None  # type: str
        if args.transfer_sh:
            if not args.quiet:
                print("Uploading file to transfer.sh ... {}".format(args.file))

            # data = aiohttp.FormData()
            # data.add_field('file',
            #                tqio(args.file),
            #                filename=file_name,
            #                content_type=file_type)

            if args.quiet:
                # Upload without any progress indicator
                with open(args.file, "rb") as f:
                    resp = loop.run_until_complete(pb._async_post_data(
                        "https://transfer.sh/",
                        # data=data))
                        data={"file": f}))
            else:
                # Upload with progress indicator
                with tqio(args.file) as f:
                    resp = loop.run_until_complete(pb._async_post_data(
                        "https://transfer.sh/",
                        # data=data))
                        data={"file": f}))
            # resp = pb._post_data("https://transfer.sh/", files={file_name: f})

            file_url = resp["raw"].strip()
            file_type = get_file_type(args.file)

        else:
            if not args.quiet:
                print("Uploading file to Pushbullet ... {}".format(args.file))
            stats = loop.run_until_complete(pb.async_upload_file(args.file))
            # stats = pb.upload_file(args.file)

            file_url = stats["file_url"]
            file_type = stats["file_type"]
            file_name = stats["file_name"]

        if not args.quiet:
            print("Pushing file ... {}".format(file_url))
        resp = loop.run_until_complete(pb.async_push_file(file_name=file_name,
                            file_type=file_type,
                            file_url=file_url,
                            title=args.title, body=args.body, device=dev))
        # resp = pb.push_file(file_name=file_name,
        #                     file_type=file_type,
        #                     file_url=file_url,
        #                     title=args.title, body=args.body, device=dev)
        if not args.quiet:
            print(resp)

        loop.run_until_complete(pb.close())
        loop.close()


    # Push note
    elif args.title or args.body:
        title = args.title
        body = args.body

        dev = None  # type: Device
        if args.device:
            dev = pb.get_device(nickname=args.device)
            if dev is None:
                print("Device not found:", args.device, file=sys.stderr)
                sys.exit(__ERR_DEVICE_NOT_FOUND__)

        if body is not None and body == "-":
            body = sys.stdin.read()
        url = args.url
        if url is None:
            resp = pb.push_note(title=title, body=body, device=dev)
        else:
            resp = pb.push_link(title=title, url=url, body=body, device=dev)

        if not args.quiet:
            print(resp)
        loop.run_until_complete(pb.close())
        loop.close()
    else:
        print("Nothing to do.")
        loop.run_until_complete(pb.close())
        loop.close()
        sys.exit(__ERR_NOTHING_TO_DO__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", help="Your Pushbullet.com API key")
    parser.add_argument("--key-file", help="Text file containing your Pushbullet.com API key")
    parser.add_argument("-t", "--title", help="Title of your push")
    parser.add_argument("-b", "--body", help="Body of your push (- means read from stdin)")
    parser.add_argument("-d", "--device", help="Destination device nickname")
    parser.add_argument("--list-devices", action="store_true", help="List registered device names")
    parser.add_argument("-u", "--url", help="URL of link being pushed")
    parser.add_argument("-f", "--file", help="Pathname to file to push")
    parser.add_argument("--transfer.sh", dest="transfer_sh", action="store_true",
                        help="Use www.transfer.sh website for uploading files (use with --file)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress all output")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(__ERR_NOTHING_TO_DO__)

    return args


@contextlib.contextmanager
def nostdout():
    save_stdout = sys.stdout
    sys.stdout = io.TextIOBase()
    yield
    sys.stdout = save_stdout



if __name__ == "__main__":
    main()
