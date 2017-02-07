#!/usr/bin/env python3
"""
A command line script for sending pushes
"""
import contextlib
import os
import argparse

import sys

import logging
from pprint import pprint

import io

sys.path.append("..")
from asyncpushbullet import Pushbullet, PushbulletError

API_KEY = ""  # YOUR API KEY
# logging.basicConfig(logging.ERROR)

# sys.argv.append("--list-devices")
sys.argv += ["--file", __file__]


# sys.argv.append("--quiet")

def main():
    args = parse_args()
    do_main(args)


def do_main(args):
    global API_KEY

    # Key
    if args.key:
        API_KEY = args.key
    if API_KEY == "":
        print(
            "You must specify an API key, either at the command line or with the PUSHBULLET_API_KEY environment variable.",
            file=sys.stderr)
        sys.exit(1)

    # Make connection
    pb = None  # type: Pushbullet
    try:
        pb = Pushbullet(API_KEY)
    except PushbulletError as exc:
        print(exc)
        sys.exit(2)

    # List devices?
    if args.list_devices:
        print("Devices:")
        for dev in pb.devices:
            print("\t", dev.nickname)

    # Transfer file?
    elif args.file:
        if not os.path.isfile(args.file):
            print("File not found:", args.file, file=sys.stderr)
            sys.exit(3)

        if not args.quiet:
            print("Uploading file ... {}".format(args.file))
        stats = pb.upload_file(args.file)

        if not args.quiet:
            print("Pushing file ... {}".format(stats["file_url"]))
        dev = None
        if args.device:
            dev = pb.get_device(args.device)
            if dev is None:
                print("Could not find device named {}".format(args.device))
                sys.exit(3)
        resp = pb.push_file(file_name=stats["file_name"], file_type=stats["file_type"], file_url=stats["file_url"],
                            title=args.title, body=args.body, device=dev)

        if not args.quiet:
            print(resp)

    # Push note
    else:
        title = args.title
        body = args.body
        resp = pb.push_note(title, body)

        if not args.quiet:
            print(resp)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", help="Your Pushbullet.com API key")
    parser.add_argument("-t", "--title", help="Title of your push")
    parser.add_argument("-b", "--body", help="Body of your push")
    parser.add_argument("-d", "--device", help="Destination device name")
    parser.add_argument("-f", "--file", help="Pathname to file to push")
    parser.add_argument("--list-devices", action="store_true", help="List registered device names")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress all output")

    args = parser.parse_args()
    return args


@contextlib.contextmanager
def nostdout():
    save_stdout = sys.stdout
    sys.stdout = io.TextIOBase()
    yield
    sys.stdout = save_stdout


if __name__ == "__main__":
    if API_KEY == "":
        if "PUSHBULLET_API_KEY" in os.environ:
            API_KEY = os.environ["PUSHBULLET_API_KEY"]
        else:
            api_file = os.path.join(os.path.dirname(__file__), "../api_key.txt")
            with open(api_file) as f:
                API_KEY = f.read().strip()
    main()
