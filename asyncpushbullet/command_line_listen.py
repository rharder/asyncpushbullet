#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A command line script for listening for pushes.

usage: command_line_listen.py [-h] [-k KEY] [--key-file KEY_FILE] [-e] [-x EXEC [EXEC ...]]
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
                        http_proxy environment variables
  --debug               Turn on debug logging
  -v, --verbose         Turn on verbose logging (INFO messages)

"""
import argparse
import asyncio
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

sys.path.append("..")
from asyncpushbullet import Device
from asyncpushbullet import InvalidKeyError
from asyncpushbullet import PushListener
from asyncpushbullet import PushbulletError
from asyncpushbullet import AsyncPushbullet

__author__ = "Robert Harder"
__email__ = "rob@iHarder.net"

# Exit codes
__ERR_API_KEY_NOT_GIVEN__ = 1
__ERR_INVALID_API_KEY__ = 2
__ERR_CONNECTING_TO_PB__ = 3
__ERR_FILE_NOT_FOUND__ = 4
__ERR_DEVICE_NOT_FOUND__ = 5
__ERR_NOTHING_TO_DO__ = 6
__ERR_UNKNOWN__ = 99

DEFAULT_THROTTLE_COUNT = 10
DEFAULT_THROTTLE_SECONDS = 10
ENCODING = "utf-8"

# sys.argv.append("-h")
# sys.argv.append("-v")
# sys.argv.append("--debug")
# sys.argv += ["-k", "badkey"]
# sys.argv += ["--key-file", "../api_key.txt"]
# sys.argv += ["--device", "Kanga"]
# sys.argv.append("--echo")
# sys.argv += ["--proxy", ""]
# sys.argv.append("--list-devices")
# sys.argv += ["--exec-simple", r"C:\windows\System32\clip.exe"]
# sys.argv += ["--exec", r"C:\windows\System32\notepad.exe"]
# sys.argv += ["--exec", r"c:\python37-32\python.exe", r"C:\Users\rharder\Documents\Programming\asyncpushbullet\examples\respond_to_listen_imagesnap.py"]
# sys.argv += ["--exec-simple", r"c:\python37-32\python.exe", r"C:\Users\rharder\Documents\Programming\asyncpushbullet\examples\respond_to_listen_exec_simple.py"]


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

    # Logging levels
    if args.debug:  # Debug?
        print("Log level: DEBUG")
        logging.basicConfig(level=logging.DEBUG)

    elif args.verbose:  # Verbose?
        print("Log level: INFO")
        logging.basicConfig(level=logging.INFO)

    # Proxy
    proxy = args.proxy or os.environ.get("https_proxy") or os.environ.get("http_proxy")

    # List devices?
    if args.list_devices:
        print("Devices:")

        pb = None  # type: AsyncPushbullet
        try:
            pb = AsyncPushbullet(api_key, proxy=proxy)
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
        proc_loop = asyncio.new_event_loop()  # Processes
        asyncio.get_child_watcher()  # Main loop

    def _run(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    threading.Thread(target=partial(_run, proc_loop), name="Thread-proc", daemon=True).start()

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
        print("No actions specified -- defaulting to Echo.")
        listen_app.add_action(EchoAction())

    loop = asyncio.get_event_loop()

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
        [
            {
                "title" : "Fish Food Served",
                "body" : "Your automated fish feeding gadget has fed your fish. "
            },
            { "title" : "Second push", "body" : "Second body" }
        ]
        

    Or simpler form for a single push:

        { "title" : "title here", "body" : "body here"}
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

    async def do(self, push: dict, app):
        """

        :param dict push:
        :param ListenApp app:
        :return:
        """
        pass

    def __repr__(self):
        return type(self).__name__


class EchoAction(Action):
    """ Echoes pushes in json format to standard out. """

    async def do(self, push: dict, app):  # pb: AsyncPushbullet):  # , device:Device):
        # json_push = json.dumps(push)
        # print(json_push, end="\n\n", flush=True)
        print("Echo push:", pprint.pformat(push))


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
            print("_ProcessProtocol.pipe_data_received", data)

        def process_exited(self):
            print("_ProcessProtocol.process_exited")

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
                input_bytes = self.transform_push_to_stdin_data(push)

                try:
                    # print("Awaiting process completion", self.path_to_executable, *self.args_for_exec)
                    self.log.debug(
                        "Awaiting process completion {}".format([self.path_to_executable, *self.args_for_exec]))
                    stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(input=input_bytes),
                                                                      timeout=self.timeout)
                except asyncio.futures.TimeoutError as e:
                    self.log.error("Execution time out after {} seconds. {}".format(self.timeout, repr(self)))
                    proc.terminate()
                else:
                    # Handle the response from the subprocess
                    # This goes back on the io_loop since it may involve
                    # responding to pushbullet.
                    if stdout_data == b'' and stderr_data == b'':
                        self.log.info("Nothing was returned from executable {}".format(
                            [self.path_to_executable, *self.args_for_exec]))
                    asyncio.run_coroutine_threadsafe(
                        self.handle_process_response(stdout_data, stderr_data, app),
                        loop=io_loop)
                finally:
                    self.log.debug("Process complete {}".format([self.path_to_executable, *self.args_for_exec]))
                    # print("Process complete", self.path_to_executable, *self.args_for_exec)

        # This Action's do() function must process on the alternate event loop
        # This is necessary mostly for the windows world where we have to have
        # a different event loop, a ProactorLoop, to handle subprocesses.
        asyncio.run_coroutine_threadsafe(_on_proc_loop(), self.proc_loop)

    def transform_push_to_stdin_data(self, push: dict) -> bytes:
        json_push = json.dumps(push)
        input_bytes = json_push.encode(ENCODING)
        return input_bytes

    async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes, app):
        """

        :param bytes stdout_data:
        :param bytes stderr_data:
        :param ListenApp app:
        :return:
        """

        # Any stderr output?
        if stderr_data != b"":
            stderr_txt = stderr_data.decode(ENCODING, "replace")
            self.log.error("Error from {}: {}".format(repr(self), stderr_data))
        else:
            stderr_txt = None  # type: str

        # Any stdout output?
        if stdout_data != b"":
            self.log.info("Response from {}: {}".format(repr(self), stdout_data))
            stdout_txt = stdout_data.decode(ENCODING, "replace")
        else:
            stdout_txt = None  # type: str

        # If there's anything to respond with, send a push back
        if stderr_txt is not None:
            title = "Error"
            body = "Stderr: {}\nStdout: {}".format(stderr_txt, stdout_txt)
            await app.respond(title=title, body=body)

        elif stdout_txt is not None:
            # See if we got a structured response with JSON data
            try:
                response = json.loads(stdout_txt)
            except json.decoder.JSONDecodeError as e:
                # Not json, just respond with a simple push
                title = "Response"
                body = stdout_txt
                await app.respond(title=title, body=body)

            else:

                async def _hndl_resp(_resp):
                    # Interpret structures response
                    title = _resp.get("title")
                    body = _resp.get("body")

                    if _resp.get("type") == "file":
                        file_type = _resp.get("file_type")
                        file_url = _resp.get("file_url")
                        file_name = _resp.get("file_name")
                        await app.respond_file(file_name=file_name,
                                               file_url=file_url,
                                               file_type=file_type,
                                               title=title,
                                               body=body)
                    else:
                        await app.respond(title=title, body=body)

                if type(response) == list:
                    for resp in response:
                        await _hndl_resp(resp)
                elif type(response) == dict:
                    await _hndl_resp(response)
                else:
                    # Not sure what was returned
                    await app.respond(title="Response", body=str(response))
        else:
            pass
            # Nothing sent back in stdout or stderr: send no push
            # print("NOTHING RETUREND FROM EXECUTABLE")


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
        output_bytes = output.encode(ENCODING)
        return output_bytes

    async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes, app):  # pb: AsyncPushbullet):

        if stdout_data != b"":
            data = stdout_data.decode(ENCODING, "replace")
            lines = data.splitlines()
            if len(lines) > 0:
                title = lines.pop(0).rstrip()
                body_lines = [line.rstrip() for line in lines]
                body = "\n".join(body_lines)
                resp = {"title": title, "body": body}
                stdout_data = json.dumps(resp).encode(ENCODING)

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
        self._listener = None  # type: PushListener
        self.app_device = None  # type: Device
        self.sent_push_idens = []  # type: List[str]
        self.persistent_connection = True
        self.persistent_connection_wait_interval = 10  # seconds between retry

    def add_action(self, action: Action):
        self.actions.append(action)
        self.log.info("Action added: {}".format(repr(action)))

    async def close(self):
        if self._listener is not None:
            await self._listener.close()
        # self.pb.close_all_threadsafe()
        await self.pb.async_close()

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

    async def respond(self, title=None, body=None, type="note", device_iden=None):
        """Actions can use this to respond to a push."""
        # print("Responding with title={}, body={}".format(title, body), flush=True)
        device = None if device_iden is None else Device(None, {"iden": device_iden})
        resp = await self.pb.async_push_note(title=title, body=body, device=device)
        self.sent_push_idens.append(resp.get("iden"))

    async def respond_file(self, file_name: str, file_url: str, file_type: str,
                           body: str = None, title: str = None, device_iden=None):

        device = None if device_iden is None else Device(None, {"iden": device_iden})
        resp = await self.pb.async_push_file(file_name=file_name,
                                             file_url=file_url,
                                             file_type=file_type,
                                             title=title,
                                             body=body,
                                             device=device)
        self.sent_push_idens.append(resp.get("iden"))

    async def run(self):
        exit_code = 0
        while self.persistent_connection:
            try:
                # If filtering on device, find or create device with that name
                if self.device_name is not None:
                    dev = await self.pb.async_get_device(nickname=self.device_name)
                    if dev is None:
                        dev = await self.pb.async_new_device(nickname=self.device_name)
                        if dev is None:
                            self.log.error("Device {} was not found and could not be created.")
                        else:
                            self.log.info("Device {} was not found, so we created it.".format(self.device_name))

                print("Connecting to pushbullet...", end="", flush=True)
                async with PushListener(self.pb, only_this_device_nickname=self.device_name) as pl2:
                    print("Connected.", flush=True)
                    self._listener = pl2

                    if self.device_name is None:
                        print("Awaiting pushes...")
                    else:
                        print("Awaiting pushes to device {}...".format(self.device_name))

                    # print("Awaiting pushes...")
                    async for push in pl2:
                        self.log.info("Received push {}".format(push))

                        await self._throttle()

                        if push.get("iden") in self.sent_push_idens:
                            # This is one we sent - ignore it
                            # print("Received a push we sent. Ignoring it.")
                            continue

                        for action in self.actions:  # type: Action
                            self.log.debug("Calling action {}".format(repr(action)))
                            try:
                                await action.do(push, self)
                                await asyncio.sleep(0)

                            except Exception as ex:
                                print("Action {} caused exception {}".format(action, ex))
                                ex.with_traceback()

            except InvalidKeyError as ex:
                exit_code = __ERR_INVALID_API_KEY__
                print(ex, file=sys.stderr, flush=True)
                self.persistent_connection = False  # Invalid key results in immediate exit

            except Exception as ex:
                print(ex, file=sys.stderr, flush=True)
                exit_code = __ERR_UNKNOWN__  # exit code

            else:
                print("Connection closed.")

            finally:
                # print("ListenApp.run() try block exiting. self.persistent_connection =", self.persistent_connection)
                if self.persistent_connection:
                    print("Waiting {} seconds to try again...".format(self.persistent_connection_wait_interval))
                    await asyncio.sleep(self.persistent_connection_wait_interval)

        return exit_code


if __name__ == "__main__":
    main()
