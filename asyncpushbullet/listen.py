#!/usr/bin/env python3
"""
A command line script for listening for pushes.

usage: listen.py [-h] [-k KEY] [--key-file KEY_FILE] [-e] [-x EXEC [EXEC ...]]
                 [-s EXEC_SIMPLE [EXEC_SIMPLE ...]]
                 [--throttle-count THROTTLE_COUNT]
                 [--throttle-seconds THROTTLE_SECONDS] [-d DEVICE]
                 [--list-devices] [--debug] [-v]

optional arguments:
  -h, --help            show this help message and exit
  -k KEY, --key KEY     Your Pushbullet.com API key
  --key-file KEY_FILE   Text file containing your Pushbullet.com API key
  -e, --echo            ACTION: Echo push as json to stdout
  -x EXEC [EXEC ...], --exec EXEC [EXEC ...]
                        ACTION: Execute a script to receive push as json via
                        stdin. Your script can write json to stdout to send
                        pushes back. { "pushes" : [ { "title" = "Fish Food
                        Served", "body" = "Your automated fish feeding gadget
                        has fed your fish. " } ] } Or simpler form for a
                        single push: { "title" = "title here", "body" = "body
                        here"}
  -s EXEC_SIMPLE [EXEC_SIMPLE ...], --exec-simple EXEC_SIMPLE [EXEC_SIMPLE ...]
                        ACTION: Execute a script to receive push in simplified
                        form via stdin. The first line of stdin will be the
                        title, and subsequent lines will be the body. Your
                        script can write lines back to stdout to send a single
                        push back. The first line of stdout will be the title,
                        and subsequent lines will be the body.
  --throttle-count THROTTLE_COUNT
                        Pushes will be throttled to this many pushes (default
                        10) in a certain number of seconds (default 10)
  --throttle-seconds THROTTLE_SECONDS
                        Pushes will be throttled to a certain number of pushes
                        (default 10) in this many seconds (default 10)
  -d DEVICE, --device DEVICE
                        Only listen for pushes targeted at given device name
  --list-devices        List registered device names
  --proxy p             Specify a proxy; otherwise use value of https_proxy or
                        http_proxy environment variable
  --debug               Turn on debug logging
  -v, --verbose         Turn on verbose logging (INFO messages)

"""
import argparse
import asyncio
import io
import json
import logging
import os
import pprint
import sys
import textwrap
import threading
import time
from functools import partial
from typing import List

from asyncpushbullet import Device
from asyncpushbullet import InvalidKeyError
from asyncpushbullet import PushListener2
from asyncpushbullet import Pushbullet
from asyncpushbullet import PushbulletError

sys.path.append("..")
from asyncpushbullet import AsyncPushbullet

__author__ = "Robert Harder"
__email__ = "rob@iHarder.net"
__encoding__ = "utf-8"

# Exit codes
__ERR_API_KEY_NOT_GIVEN__ = 1
__ERR_INVALID_API_KEY__ = 2
__ERR_CONNECTING_TO_PB__ = 3
__ERR_FILE_NOT_FOUND__ = 4
__ERR_DEVICE_NOT_FOUND__ = 5
__ERR_NOTHING_TO_DO__ = 6
__ERR_UNKNOWN__ = 99

# sys.argv.append("-h")
# sys.argv += ["-k", "badkey"]
sys.argv += ["--key-file", "../api_key.txt"]
# sys.argv.append("--echo")
# sys.argv += ["--proxy", ""]
# sys.argv.append("--list-devices")
# sys.argv += ["--exec", r"C:\windows\System32\clip.exe"]
# sys.argv += ["--exec", r"C:\windows\System32\notepad.exe"]
sys.argv += ["--exec", r"c:\python37-32\python.exe",
             r"C:\Users\rharder\Documents\Programming\asyncpushbullet\examples\respond_to_listen_exec.py"]
# sys.argv += ["--exec", r"c:\python37-32\python.exe", r"C:\Users\rharder\Documents\Programming\asyncpushbullet\examples\hello.py"]
# sys.argv += ["--exec", r"C:\windows\System32\notepad.exe", r"C:\Users\rharder\Documents\Programming\asyncpushbullet\examples\respond_to_listen_exec.py"]

logging.basicConfig(level=logging.DEBUG)

DEFAULT_THROTTLE_COUNT = 10
DEFAULT_THROTTLE_SECONDS = 10


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

    # List devices?
    if args.list_devices:
        print("Devices:")

        pb = None  # type: Pushbullet
        try:
            pb = Pushbullet(api_key, proxy=proxy)
            pb.verify_key()
        except InvalidKeyError as exc:
            print(exc, file=sys.stderr)
            sys.exit(__ERR_INVALID_API_KEY__)
        except PushbulletError as exc:
            print(exc, file=sys.stderr)
            sys.exit(__ERR_CONNECTING_TO_PB__)
        else:
            for dev in pb.devices:
                print("\t", dev.nickname)
            sys.exit(0)

    # Throttle
    throttle_count = args.throttle_count
    throttle_seconds = args.throttle_seconds

    # Device
    device = args.device

    # Create ListenApp
    listen_app = ListenApp(api_key,
                           proxy=proxy,
                           throttle_count=throttle_count,
                           throttle_seconds=throttle_seconds,
                           device=device)

    # Windows needs special event loop in order to launch processes on it
    proc_loop = None  # type: asyncio.BaseEventLoop
    if sys.platform == 'win32':
        proc_loop = asyncio.ProactorEventLoop()
        print("On win32--using ProactorEventLoop.")
    else:
        proc_loop = asyncio.new_event_loop()

    def _run(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    threading.Thread(target=partial(_run, proc_loop), name="Thread-proc", daemon=True).start()
    # t = threading.Thread(target=partial(_run, proc_loop))
    # t.daemon = True
    # t.start()

    # Add actions from command line arguments
    if args.exec:
        for cmd_opts in args.exec:
            cmd_path = cmd_opts[0]
            cmd_args = cmd_opts[1:]
            action = ExecutableAction(cmd_path, cmd_args, loop=proc_loop)
            listen_app.add_action(action)

    # Add actions from command line arguments
    if args.exec_simple:
        for cmd_opts in args.exec_simple:
            cmd_path = cmd_opts[0]
            cmd_args = cmd_opts[1:]
            action = ExecutableActionSimplified(cmd_path, cmd_args, loop=proc_loop)
            listen_app.add_action(action)

    # Default action if none specified
    if len(listen_app.actions) == 0 or args.echo:
        listen_app.add_action(EchoAction())

    loop = asyncio.get_event_loop()

    # async def _timeout():
    #     await asyncio.sleep(2)
    #     await listen_app.close()
    # loop.create_task(_timeout())

    exit_code = None
    try:
        exit_code = loop.run_until_complete(listen_app.run())
    except KeyboardInterrupt as e:
        print("Caught keyboard interrupt")
    finally:
        loop.run_until_complete(listen_app.close())
        if exit_code is None:
            exit_code = 0
        sys.exit(exit_code)
        # END OF PROGRAM


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", help="Your Pushbullet.com API key")
    parser.add_argument("--key-file", help="Text file containing your Pushbullet.com API key")
    parser.add_argument("-e", "--echo", action="store_true", help="ACTION: Echo push as json to stdout")
    parser.add_argument("-x", "--exec", nargs="+", action="append",
                        help=textwrap.dedent("""
                        ACTION: Execute a script to receive push as json via stdin.
                        Your script can write json to stdout to send pushes back.

        {
            "pushes" :
                [
                    {
                        "title" = "Fish Food Served",
                        "body" = "Your automated fish feeding gadget has fed your fish. "
                     }
                ]
        }

    Or simpler form for a single push:

        { "title" = "title here", "body" = "body here"}
                        """))
    parser.add_argument("-s", "--exec-simple", nargs="+", action="append",
                        help=textwrap.dedent("""
                        ACTION: Execute a script to receive push in simplified form
                        via stdin.  The first line of stdin will be the title, and
                        subsequent lines will be the body.
                        Your script can write lines back to stdout to send a single
                        push back.  The first line of stdout will be the title, and
                        subsequent lines will be the body.
                        """))

    parser.add_argument("--throttle-count", type=int, default=DEFAULT_THROTTLE_COUNT,
                        help=textwrap.dedent("""
                        Pushes will be throttled to this many pushes (default {})
                        in a certain number of seconds (default {})"""
                                             .format(DEFAULT_THROTTLE_COUNT,
                                                     DEFAULT_THROTTLE_SECONDS)))
    parser.add_argument("--throttle-seconds", type=int, default=DEFAULT_THROTTLE_SECONDS,
                        help=textwrap.dedent("""
                        Pushes will be throttled to a certain number of pushes (default {})
                        in this many seconds (default {})"""
                                             .format(DEFAULT_THROTTLE_COUNT,
                                                     DEFAULT_THROTTLE_SECONDS)))

    parser.add_argument("-d", "--device", help="Only listen for pushes targeted at given device name")
    parser.add_argument("--list-devices", action="store_true", help="List registered device names")
    parser.add_argument("--proxy", help="Optional web proxy")
    parser.add_argument("--debug", action="store_true", help="Turn on debug logging")
    parser.add_argument("-v", "--verbose", action="store_true", help="Turn on verbose logging (INFO messages)")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(__ERR_NOTHING_TO_DO__)

    return args


class Action:
    """ Base class for actions that this listener will take upon receiving new pushes. """

    def __init__(self):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

    async def do(self, push: dict, app):  # pb: AsyncPushbullet):#, device: Device):
        """

        :param push:
        :param ListenApp app:
        :return:
        """
        pass

    def __repr__(self):
        return type(self).__name__


class EchoAction(Action):
    """ Echoes pushes in json format to standard out. """

    async def do(self, push: dict, app):  # pb: AsyncPushbullet):  # , device:Device):
        json_push = json.dumps(push)
        print(json_push, end="\n\n", flush=True)


class ExecutableAction(Action):
    """
    Interprets subprocess response from stdout as JSON data requesting pushes being returned.

    Example response from subprocess:

        {
            "pushes" :
                [
                    {
                        "title" = "Fish Food Served",
                        "body" = "Your automated fish feeding gadget has fed your fish. "
                     }
                ]
        }

    Or simpler form for a single push:

        { "title" = "title here", "body" = "body here"}
    """

    class _ProcessProtocol(asyncio.SubprocessProtocol):
        def __init__(self, action):
            self.transport = None
            self.action = action  # parent

        def connection_made(self, transport):
            # print("connection_made", transport)
            self.transport = transport

        def pipe_data_received(self, fd, data):
            print("pipe_data_received", data)

        def process_exited(self):
            print("process_exited")

    def __init__(self, path_to_executable, args_for_exec=(), loop: asyncio.BaseEventLoop = None, timeout=30):
        super().__init__()
        self.path_to_executable = path_to_executable
        self.args_for_exec = args_for_exec
        self.protocol = ExecutableAction._ProcessProtocol(self)
        self.timeout = timeout
        self.proc_loop = loop

        if not os.path.isfile(path_to_executable):
            self.log.warning("Executable not found at launch time.  " +
                             "Will still attempt to run when pushes are received. ({})"
                             .format(path_to_executable))

    def __repr__(self):
        return "{}({} {})".format(super().__repr__(), self.path_to_executable, " ".join(self.args_for_exec))

    async def do(self, push: dict, app):  # pb: AsyncPushbullet):  # , device:Device):
        io_loop = asyncio.get_event_loop()  # Loop handling the pushbullet IO

        async def _on_proc_loop():
            # Launch process
            try:
                print("Launching process", self.path_to_executable, *self.args_for_exec)
                proc = await asyncio.create_subprocess_exec(self.path_to_executable,
                                                            *self.args_for_exec,
                                                            stdin=asyncio.subprocess.PIPE,
                                                            stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.PIPE)
            except Exception as e:
                self.log.error("Error occurred while trying to launch executable. ({}): {}"
                               .format(self.path_to_executable, e))

            else:

                # Pass the incoming push via stdin (json form)
                json_push = json.dumps(push)
                input_bytes = json_push.encode(__encoding__)

                try:
                    stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(input=input_bytes),
                                                                      timeout=self.timeout)
                except asyncio.futures.TimeoutError as e:
                    self.log.error("Execution time out after {} seconds. {}".format(self.timeout, repr(self)))
                    proc.terminate()
                else:
                    # Process response from subprocess
                    asyncio.run_coroutine_threadsafe(
                        self.handle_process_response(stdout_data, stderr_data, app),
                        loop=io_loop)
                    pass

        asyncio.run_coroutine_threadsafe(_on_proc_loop(), self.proc_loop)

    async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes, app):
        # pb: AsyncPushbullet):  # , device:Device):
        print("handle_process_response")
        # stdout_data = b"hello world"
        # await asyncio.sleep(1)

        # There's a problem with a push be sent in response and then that push is responded
        # to etc and then an infinite loop.

        # raise Exception("Not yet implemented.")

        # Any stderr output?
        if stderr_data != b"":
            self.log.error("Error from {}: {}".format(repr(self), stderr_data))
            await app.respond(title="Error", body=str(stderr_data))

        # Any stdout output?
        if stdout_data != b"":
            self.log.info("Response from {}: {}".format(repr(self), stdout_data))

            # Requesting a response push?
            resp = {}
            raw_data = None
            try:
                print("Decoding this:")
                raw_data = stdout_data.decode(__encoding__, "replace")
                print(raw_data)
                resp = json.loads(raw_data)
            # except json.decoder.JSONDecodeError as e:
            except Exception as e:
                resp["body"] = raw_data
                resp["error"] = str(e)
                print("NEW RESPONSE:")
                pprint.pprint(resp)

                pass

            # Single push response
            title = str(resp.get("title"))
            body = str(resp.get("body"))
            if resp.get("type") == "file":
                print("SENDING FILE PUSH")
                file_type = resp.get("file_type")
                file_url = resp.get("file_url")
                file_name = resp.get("file_name")
                await app.respond_file(file_name=file_name,
                                       file_url=file_url,
                                       file_type=file_type,
                                       title=title,
                                       body=body)

            elif "title" in resp or "body" in resp:
                print("basic response")
                await app.respond(body=body, title=title)
            # push_resp = await pb.async_push_note(title=title, body=body)

            # push_resp = await device.push_note(title=title, body=body)
            # print("Push Resp:", push_resp)

            # Multiple pushes response
            # pushes = resp.get("pushes", [])
            # if type(pushes) == list:
            #     for push in pushes:  # type: dict
            #         if type(push) == dict:
            #             title = push.get("title", "no title")
            #             body = push.get("body", "no body")
            #             # await pb.async_push_note(title=title, body=body)
            #         else:
            #             self.log.error("A push response was received but was not in dictionary form: {}".format(resp))
            pass
            pass
            print("exiting handle_process_response")
            pass


class ExecutableActionSimplified(ExecutableAction):
    """
    Interprets subprocess response from stdout as line1 = title and remaining lines = body.

    Example response from subprocess:

        Fish Food Served
        Your automated fish feeding gadget has fed your fish.

    """

    def transform_push_to_stdin_data(self, push: dict) -> bytes:
        title = str(push.get("title", "")).strip().replace("\n", " ")
        body = str(push.get("body", ""))
        output = "{}\n{}".format(title, body)
        output_bytes = output.encode(__encoding__)
        return output_bytes

    async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes, app):  # pb: AsyncPushbullet):

        if stdout_data != b"":
            data = stdout_data.decode(__encoding__, "replace")
            lines = data.splitlines()
            if len(lines) > 0:
                title = lines.pop(0).rstrip()
                body_lines = [line.rstrip() for line in lines]
                body = "\n".join(body_lines)
                resp = {"pushes": [{"title": title, "body": body}]}
                stdout_data = json.dumps(resp).encode(__encoding__)

        await super().handle_process_response(stdout_data=stdout_data, stderr_data=stderr_data, app=app)  # pb=pb)


class ListenApp:
    def __init__(self, api_key: str,
                 proxy: str = None,
                 throttle_count: int = DEFAULT_THROTTLE_COUNT,
                 throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
                 device: str = None):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.pb = AsyncPushbullet(api_key=api_key, proxy=proxy)
        self.throttle_max_count = throttle_count
        self.throttle_max_seconds = throttle_seconds
        self.device_name = device
        self._throttle_timestamps = []  # type: [float]
        self.actions = []  # type: [Action]
        self._listener = None  # type: PushListener2
        self.app_device = None  # type: Device
        self.sent_push_idens = []  # type: List[str]

    def add_action(self, action: Action):
        self.actions.append(action)
        self.log.info("Action added: {}".format(repr(action)))

    async def close(self):
        if self._listener is not None:
            await self._listener.close()
        self.pb.close_all_threadsafe()

    async def _throttle(self):
        """ Makes one tick and stalls if necessary """

        self._throttle_timestamps.append(time.time())  # tick!
        if len(self._throttle_timestamps) > self.throttle_max_count:  # limit list size
            self._throttle_timestamps.pop(0)

        span = self._throttle_timestamps[-1] - self._throttle_timestamps[0]  # span between first and last

        # Stall enough so that the next push won't get throttled
        if len(self._throttle_timestamps) >= self.throttle_max_count and span < self.throttle_max_seconds:
            future_time = self._throttle_timestamps[1] + self.throttle_max_seconds
            stall = future_time - time.time()
            self.log.warning("Throttling pushes that are coming too fast. Stalling {:0.1f} seconds ...".format(stall))
            await asyncio.sleep(stall)

    async def respond(self, title=None, body=None, type="note"):
        """Actions can use this to respond to a push."""
        print("Responding with title={}, body={}".format(title, body), flush=True)
        resp = await self.pb.async_push_note(title=title, body=body)
        self.sent_push_idens.append(resp.get("iden"))

    async def respond_file(self, file_name: str, file_url: str, file_type: str,
                           body: str = None, title: str = None) -> dict:
        print("Responding with file push")
        resp = await self.pb.async_push_file(file_name=file_name,
                                             file_url=file_url,
                                             file_type=file_type,
                                             title=title,
                                             body=body)
        self.sent_push_idens.append(resp.get("iden"))

    async def run(self):
        try:
            # self.app_device = await self.pb.async_get_device(nickname="ListenApp")
            # if self.app_device is None:
            #     self.app_device = await self.pb.async_new_device(nickname="ListenApp")
            # token = "randomdata"
            # setattr(self.app_device, "push_token", token)
            # print("ListenApp using device:", repr(self.app_device))

            async with PushListener2(self.pb, only_this_device_nickname=self.device_name) as pl2:
                self._listener = pl2

                # Warn if device is not known at launch
                if self.device_name is not None:
                    dev = await self.pb.async_get_device(nickname=self.device_name)
                    if dev is None:
                        self.log.warning("Device {} not found at launch time.  ".format(self.device_name) +
                                         "Will still attempt to filter as pushes are received.")
                    del dev

                print("Awaiting pushes...")
                async for push in pl2:
                    self.log.info("Received push {}".format(push))

                    await self._throttle()

                    if push.get("iden") in self.sent_push_idens:
                        # This is one we sent - ignore it
                        print("Received a push we sent. Ignoring it.")
                        continue

                    # First ignore pushes that came from this app
                    if "source_device_iden" in push:
                        if push["source_device_iden"] == self.app_device.device_iden:
                            # Ignore this push
                            print("Got a push from myself. Ignoring it:", push)
                            continue  # next push in pl2

                    for action in self.actions:  # type: Action
                        self.log.debug("Calling action {}".format(repr(action)))
                        try:
                            await action.do(push, self)  # self.pb)  # , self.app_device)
                            await asyncio.sleep(0)
                        except Exception as ex:
                            print("Action {} caused exception {}".format(action, ex))

        except Exception as ex:
            print("listenapp.run exception:", ex)
            ex.with_traceback()
            return __ERR_UNKNOWN__  # exit code

        return 0


if __name__ == "__main__":
    main()
