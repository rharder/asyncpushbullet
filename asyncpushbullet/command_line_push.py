#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A command line script for sending pushes.

This file contains entry points for both pbpush and pbtransfer.

usage: command_line_push.py [-h] [-k KEY] [--key-file KEY_FILE]
                            [--proxy PROXY] [-t TITLE] [-b BODY] [-d DEVICE]
                            [--list-devices] [-u URL] [-f FILE]
                            [--transfer.sh] [-q] [--oauth2] [--debug] [-v]
                            [--version]

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
  --oauth2              Register your command line tool using OAuth2
  --debug               Turn on debug logging
  -v, --verbose         Turn on verbose logging (INFO messages)
  --version             show program's version number and exit


"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Dict

from asyncpushbullet import AsyncPushbullet, __version__
from asyncpushbullet import Device
from asyncpushbullet import InvalidKeyError, PushbulletError
from asyncpushbullet import errors
from asyncpushbullet import oauth2
from asyncpushbullet.command_line_listen import try_to_find_key


def main():
    # sys.argv.append("--help")
    # sys.argv.append("--quiet")
    # sys.argv += ["--key", "badkey"]
    # sys.argv += ["--key-file", "../api_key.txt"]

    # sys.argv.append("--oauth2")
    # sys.argv.append("--version")
    # sys.argv.append("--list-devices")
    # sys.argv += ["-t", "test to device", "--device", "baddevice"]
    # sys.argv += ["-d", "Kanga"]
    # sys.argv += ["-t", "my title", "-b", "foo"]
    # sys.argv += ["-t", "Read stdin", "-b", "-"]

    # sys.argv += [ "--file", __file__]
    # sys.argv += [__file__]

    # sys.argv += ["--file", "badfile.txt"]
    # sys.argv.append("--transfer.sh")

    # sys.argv += ["-t", "foo"]

    main_pbpush()  # Default
    # main_pbtransfer()


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
        exit_code = errors.__ERR_KEYBOARD_INTERRUPT__
    except Exception as ex:
        print("Error:", ex, file=sys.stderr)
        exit_code = errors.__ERR_UNKNOWN__
    finally:
        return exit_code or 0


async def _run(args):
    # Logging levels
    if args.debug:  # Debug?
        print("Log level: DEBUG")
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose:  # Verbose?
        print("Log level: INFO")
        logging.basicConfig(level=logging.INFO)

    # Request setting up oauth2 access?
    if args.oauth2:
        token = await oauth2.async_gain_oauth2_access()
        if token:
            print("Successfully authenticated using OAuth2.")
            print("You should now be able to use the command line tools without specifying an API key.")
            sys.exit(0)
        else:
            print("There was a problem authenticating.")
            sys.exit(1)

    # Find a valid API key
    api_key = try_to_find_key(args, not args.quiet)
    if api_key is None:
        print("You must specify an API key.", file=sys.stderr)
        sys.exit(errors.__ERR_API_KEY_NOT_GIVEN__)

    # Proxy
    proxy = lambda: args.proxy or os.environ.get("https_proxy") or os.environ.get("http_proxy")

    try:
        # List devices?
        if args.list_devices:
            print("Devices:")
            async with AsyncPushbullet(api_key, proxy=proxy()) as pb:
                async for dev in pb.devices_asynciter():
                    print("\t", dev.nickname)
            return errors.__EXIT_NO_ERROR__

        # Specify a device?
        target_device = None  # type: Device
        if args.device:
            async with AsyncPushbullet(api_key, proxy=proxy()) as pb:
                target_device = await pb.async_get_device(nickname=args.device)

            if target_device is None:
                print("Device not found:", args.device, file=sys.stderr)
                return errors.__ERR_DEVICE_NOT_FOUND__
            else:
                print("Target device:", target_device.nickname)

        # Transfer single file?
        if getattr(args, "file", False):
            async with AsyncPushbullet(api_key, proxy=proxy()) as pb:
                return await _transfer_file(pb=pb,
                                            file_path=args.file,
                                            use_transfer_sh=args.transfer_sh,
                                            quiet=args.quiet,
                                            title=args.title,
                                            body=args.body,
                                            target_device=target_device)

        elif getattr(args, "files", False):
            async with AsyncPushbullet(api_key, proxy=proxy()) as pb:
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

            async with AsyncPushbullet(api_key, proxy=proxy()) as pb:
                if args.body is not None and args.body == "-":
                    body = sys.stdin.read().rstrip()
                else:
                    body = args.body
                url = args.url
                if url is None:
                    if not args.quiet:
                        print("Pushing note...", end="", flush=True)
                    _ = await pb.async_push_note(title=args.title, body=body, device=target_device)
                    if not args.quiet:
                        print("Done.", flush=True)
                else:
                    if not args.quiet:
                        print("Pushing link...")
                    _ = await pb.async_push_link(title=args.title, url=url, body=body, device=target_device)
                    if not args.quiet:
                        print("Done.", flush=True)

        else:
            print("Nothing to do.")
            return errors.__ERR_NOTHING_TO_DO__

    except InvalidKeyError as exc:
        print(exc, file=sys.stderr)
        return errors.__ERR_INVALID_API_KEY__

    except PushbulletError as exc:
        print(exc, file=sys.stderr)
        return errors.__ERR_CONNECTING_TO_PB__


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
        return errors.__ERR_FILE_NOT_FOUND__

    show_progress = not quiet
    if use_transfer_sh:
        if not quiet:
            print("Uploading file to transfer.sh ... {}".format(file_path))

        info: Dict = await pb.async_upload_file_to_transfer_sh(file_path=file_path,
                                                               show_progress=show_progress)

    else:
        if not quiet:
            print("Uploading file to Pushbullet ... {}".format(file_path))
        info: Dict = await pb.async_upload_file(file_path=file_path,
                                                show_progress=show_progress)

    file_url: str = info["file_url"]
    file_type: str = info["file_type"]
    file_name: str = info["file_name"]
    if not quiet:
        print("Pushing file ... {}".format(file_url))

    title = title or "File: {}".format(file_name)
    await pb.async_push_file(file_name=file_name,
                             file_type=file_type,
                             file_url=file_url,
                             title=title,
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
    parser.add_argument("--oauth2", action="store_true", help="Register your command line tool using OAuth2")
    parser.add_argument("--debug", action="store_true", help="Turn on debug logging")
    parser.add_argument("-v", "--verbose", action="store_true", help="Turn on verbose logging (INFO messages)")
    parser.add_argument("--version", action="version", version='%(prog)s ' + __version__)

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(errors.__ERR_NOTHING_TO_DO__)

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
    parser.add_argument("--oauth2", action="store_true", help="Register your command line tool using OAuth2")
    parser.add_argument("--debug", action="store_true", help="Turn on debug logging")
    parser.add_argument("-v", "--verbose", action="store_true", help="Turn on verbose logging (INFO messages)")
    parser.add_argument("--version", action="version", version='%(prog)s ' + __version__)

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(errors.__ERR_NOTHING_TO_DO__)

    # Emulate the arguments used in the regular push function
    setattr(args, "transfer_sh", True)
    setattr(args, "title", None)
    setattr(args, "body", None)

    return args


if __name__ == "__main__":
    main()
