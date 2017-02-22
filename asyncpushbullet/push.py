#!/usr/bin/env python3
"""
A command line script for sending pushes.

usage: push.py [-h] [-k KEY] [--key-file KEY_FILE] [-t TITLE] [-b BODY]
               [-u URL] [-f FILE] [--transfer.sh] [--list-devices] [-q]

optional arguments:
  -h, --help            show this help message and exit
  -k KEY, --key KEY     Your Pushbullet.com API key
  --key-file KEY_FILE   Text file containing your Pushbullet.com API key
  -t TITLE, --title TITLE
                        Title of your push
  -b BODY, --body BODY  Body of your push (- means read from stdin)
  -u URL, --url URL     URL of link being pushed
  -f FILE, --file FILE  Pathname to file to push
  --transfer.sh         Use transfer.sh website for uploading files (use with
                        --file)
  --list-devices        List registered device names
  -q, --quiet           Suppress all output

"""
import argparse
import contextlib
import io
import os
import sys

sys.path.append("..")  # To help when running examples direct from the source repository
from asyncpushbullet.filetype import get_file_type
from asyncpushbullet import Pushbullet, PushbulletError


# logging.basicConfig(logging.ERROR)

# sys.argv.append("--help")
# sys.argv.append("--list-devices")
# sys.argv += ["--file", __file__]
# sys.argv.append("--transfer.sh")

# sys.argv += ["-t", "foo"]
# sys.argv += ["--key-file", "../api_key.txt"]

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
        sys.exit(1)

    # Make connection
    pb = None  # type: Pushbullet
    try:
        pb = Pushbullet(api_key)
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

        if args.transfer_sh:
            if not args.quiet:
                print("Uploading file to transfer.sh ... {}".format(args.file))
            with open(args.file, "rb") as f:
                file_name = os.path.basename(args.file)
                resp = pb._post_data("https://transfer.sh/", files={file_name: f})
                file_url = resp["raw"].strip()
                file_type = get_file_type(f, args.file)
                resp = pb.push_file(file_type=file_type, file_name=file_name,
                                    file_url=file_url, title=args.title,
                                    body=args.body)
            print(resp)

        else:
            if not args.quiet:
                print("Uploading file to Pushbullet ... {}".format(args.file))
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
    elif args.title or args.body:
        title = args.title
        body = args.body
        if body is not None and body == "-":
            body = sys.stdin.read()
        url = args.url
        if url is None:
            resp = pb.push_note(title=title, body=body)
        else:
            resp = pb.push_link(title=title, url=url, body=body)

        if not args.quiet:
            print(resp)
    else:
        print("Nothing to do.")
        sys.exit(4)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", help="Your Pushbullet.com API key")
    parser.add_argument("--key-file", help="Text file containing your Pushbullet.com API key")
    parser.add_argument("-t", "--title", help="Title of your push")
    parser.add_argument("-b", "--body", help="Body of your push (- means read from stdin)")
    # parser.add_argument("-d", "--device", help="Destination device name")
    parser.add_argument("-u", "--url", help="URL of link being pushed")
    parser.add_argument("-f", "--file", help="Pathname to file to push")
    parser.add_argument("--transfer.sh", dest="transfer_sh", action="store_true",
                        help="Use transfer.sh website for uploading files (use with --file)")
    parser.add_argument("--list-devices", action="store_true", help="List registered device names")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress all output")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(5)

    return args


@contextlib.contextmanager
def nostdout():
    save_stdout = sys.stdout
    sys.stdout = io.TextIOBase()
    yield
    sys.stdout = save_stdout


if __name__ == "__main__":
    main()
