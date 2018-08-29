#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A command line script for sending pushes.

This file contains entry points for both pbpush and pbtransfer.

usage: command_line_push.py [-h] [-k KEY] [--key-file KEY_FILE]
                            [--proxy PROXY] [-t TITLE] [-b BODY] [-d DEVICE]
                            [--list-devices] [-u URL] [-f FILE]
                            [--transfer.sh] [-q]

optional arguments:
  -h, --help            show this help message and exit
  -k KEY, --key KEY     Your Pushbullet.com API key
  --key-file KEY_FILE   Text file containing your Pushbullet.com API key
  --proxy PROXY         Optional web proxy
  -t TITLE, --title TITLE
                        Title of your push
  -b BODY, --body BODY  Body of your push (- means read from stdin)
  -d DEVICE, --device DEVICE
                        Destination device nickname
  --list-devices        List registered device names
  -u URL, --url URL     URL of link being pushed
  -f FILE, --file FILE  Pathname to file to push
  --transfer.sh         Use www.transfer.sh website for uploading files (use
                        with --file)
  -q, --quiet           Suppress all output

"""
import argparse
import asyncio
import os
import sys
from typing import List

from asyncpushbullet import AsyncPushbullet
from asyncpushbullet import Device
from asyncpushbullet import InvalidKeyError
from asyncpushbullet import PushbulletError

# Exit codes
__ERR_API_KEY_NOT_GIVEN__ = 1
__ERR_INVALID_API_KEY__ = 2
__ERR_CONNECTING_TO_PB__ = 3
__ERR_FILE_NOT_FOUND__ = 4
__ERR_DEVICE_NOT_FOUND__ = 5
__ERR_NOTHING_TO_DO__ = 6
__ERR_KEYBOARD_INTERRUPT__ = 7
__ERR_UNKNOWN__ = 99


# logging.basicConfig(logging.ERROR)

# sys.argv.append("--help")
# sys.argv.append("--quiet")
# sys.argv += ["--key", "badkey"]
# sys.argv += ["--key-file", "../api_key.txt"]

# sys.argv.append("--list-devices")
# sys.argv += ["-t", "test to device", "--device", "baddevice"]
# sys.argv += ["-t", "my title", "-b", "my body"]
# sys.argv += ["-t", "Read stdin", "-b", "-"]

# sys.argv += [ "--file", __file__]
# sys.argv += [__file__]


# sys.argv += ["--file", "badfile.txt"]
# sys.argv.append("--transfer.sh")

# sys.argv += ["-t", "foo"]


def main_pbpush():
    """Intended entry point for pbpush"""
    args = parse_args_pbpush()
    do_main(args)


def main_pbtransfer():
    """Intended entry point for pbtransfer"""
    args = parse_args_pbtransfer()
    do_main(args)


def do_main(args):
    loop = asyncio.get_event_loop()
    exit_code = None
    try:
        exit_code = loop.run_until_complete(_run(args))
    except KeyboardInterrupt:
        exit_code = __ERR_KEYBOARD_INTERRUPT__
    except Exception as ex:
        print("Error:", ex, file=sys.stderr)
        exit_code = __ERR_UNKNOWN__
    finally:
        return exit_code or 0


async def _run(args):
    # Key
    api_key = ""
    if "PUSHBULLET_API_KEY" in os.environ:
        api_key = os.environ["PUSHBULLET_API_KEY"].strip()
        if not args.quiet:
            print("API key retrieved from environment variable PUSHBULLET_API_KEY")

    if args.key_file:
        with open(args.key_file) as f:
            api_key = f.read().strip()
        if not args.quiet:
            print("API key read from file {}".format(args.key_file))

    if args.key:
        api_key = args.key.strip()
        if not args.quiet:
            print("API key retrieved from command line argument")

    if api_key == "":
        print(
            "You must specify an API key, either at the command line or with the PUSHBULLET_API_KEY environment variable.",
            file=sys.stderr)
        return __ERR_API_KEY_NOT_GIVEN__

    # Proxy
    proxy = args.proxy or os.environ.get("https_proxy") or os.environ.get("http_proxy")

    try:
        async with AsyncPushbullet(api_key, proxy=proxy) as pb:

            # List devices?
            if args.list_devices:
                print("Devices:")
                devs = await pb.async_get_devices()  # type: List[Device]
                for dev in devs:
                    print("\t", dev.nickname)
                return

            # Specify a device?
            target_device = None  # type: Device
            if args.device:
                target_device = await pb.async_get_device(nickname=args.device)
                if target_device is None:
                    print("Device not found:", args.device, file=sys.stderr)
                    return __ERR_DEVICE_NOT_FOUND__

            # Transfer single file?
            if getattr(args, "file", False):
                return await _transfer_file(pb=pb,
                                            file_path=args.file,
                                            use_transfer_sh=args.transfer_sh,
                                            quiet=args.quiet,
                                            title=args.title,
                                            body=args.body,
                                            target_device=target_device)

            elif getattr(args, "files", False):
                for file_path in args.files:  # type str
                    _ = await _transfer_file(pb=pb,
                                             file_path=file_path,
                                             use_transfer_sh=args.transfer_sh,
                                             quiet=args.quiet,
                                             title=args.title,
                                             body=args.body,
                                             target_device=target_device)


            # Push note
            elif args.title or args.body:

                if args.body is not None and args.body == "-":
                    body = sys.stdin.read().rstrip()
                else:
                    body = args.body
                url = args.url
                if url is None:
                    if not args.quiet:
                        print("Pushing note...")
                    _ = await pb.async_push_note(title=args.title, body=body, device=target_device)
                else:
                    if not args.quiet:
                        print("Pushing link...")
                    _ = await pb.async_push_link(title=args.title, url=url, body=body, device=target_device)

            else:
                print("Nothing to do.")
                return __ERR_NOTHING_TO_DO__

    except InvalidKeyError as exc:
        print(exc, file=sys.stderr)
        return __ERR_INVALID_API_KEY__

    except PushbulletError as exc:
        print(exc, file=sys.stderr)
        return __ERR_CONNECTING_TO_PB__


# Transfer file sub-function
async def _transfer_file(pb: AsyncPushbullet,
                         file_path: str,
                         use_transfer_sh: bool = True,
                         quiet: bool = False,
                         title: str = None,
                         body: str = None,
                         target_device: Device = None):
    if not os.path.isfile(file_path):
        print("File not found:", file_path, file=sys.stderr)
        return __ERR_FILE_NOT_FOUND__

    info = {}
    show_progress = not quiet
    if use_transfer_sh:
        if not quiet:
            print("Uploading file to transfer.sh ... {}".format(file_path))

        info = await pb.async_upload_file_to_transfer_sh(file_path=file_path,
                                                         show_progress=show_progress)

    else:
        if not quiet:
            print("Uploading file to Pushbullet ... {}".format(file_path))
        info = await pb.async_upload_file(file_path=file_path,
                                          show_progress=show_progress)

    file_url = info["file_url"]
    file_type = info["file_type"]
    file_name = info["file_name"]
    if not quiet:
        print("Pushing file ... {}".format(file_url))

    _ = await pb.async_push_file(file_name=file_name,
                                 file_type=file_type,
                                 file_url=file_url,
                                 title=title or "File: {}".format(file_name),
                                 body=body or file_url,
                                 device=target_device)


def parse_args_pbpush():

    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", help="Your Pushbullet.com API key")
    parser.add_argument("--key-file", help="Text file containing your Pushbullet.com API key")
    parser.add_argument("--proxy", help="Optional web proxy")
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


def parse_args_pbtransfer():

    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", help="Your Pushbullet.com API key")
    parser.add_argument("--key-file", help="Text file containing your Pushbullet.com API key")
    parser.add_argument("--proxy", help="Optional web proxy")
    parser.add_argument("-d", "--device", help="Destination device nickname")
    parser.add_argument("--list-devices", action="store_true", help="List registered device names")
    parser.add_argument("-f", "--file", help="Pathname to file to push")
    parser.add_argument('files', nargs='*', help="Remaining arguments will be files to push")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress all output")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(__ERR_NOTHING_TO_DO__)

    # Emulate the arguments used in the regular push function
    setattr(args, "transfer_sh", True)
    setattr(args, "title", None)
    setattr(args, "body", None)

    return args


if __name__ == "__main__":
    main_pbpush()  # Default
