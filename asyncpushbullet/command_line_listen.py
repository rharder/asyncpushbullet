#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A command line script for listening for pushes.

usage: command_line_listen.py [-h] [-k KEY] [--key-file KEY_FILE] [-e]
                              [-x EXEC [EXEC ...]]
                              [-s EXEC_SIMPLE [EXEC_SIMPLE ...]]
                              [-p EXEC_PYTHON [EXEC_PYTHON ...]] [-t TIMEOUT]
                              [--throttle-count THROTTLE_COUNT]
                              [--throttle-seconds THROTTLE_SECONDS]
                              [-d DEVICE] [--list-devices] [--proxy PROXY]
                              [--debug] [-v] [-q] [--oauth2] [--clear-oauth2]
                              [--version]

optional arguments:
  -h, --help            show this help message and exit
  -k KEY, --key KEY     Your Pushbullet.com API key
  --key-file KEY_FILE   Text file containing your Pushbullet.com API key
  -e, --echo            ACTION: Echo push as json to stdout
  -x EXEC [EXEC ...], --exec EXEC [EXEC ...]
                        ACTION: Execute a script to receive push as json via
                        stdin. Your script can write json to stdout to send
                        pushes back. [ { "title" : "Fish Food Served", "body"
                        : "Your automated fish feeding gadget has fed your
                        fish. " }, { "title" : "Second push", "body" : "Second
                        body" } ] Or simpler form for a single push: { "title"
                        : "title here", "body" : "body here"}
  -s EXEC_SIMPLE [EXEC_SIMPLE ...], --exec-simple EXEC_SIMPLE [EXEC_SIMPLE ...]
                        ACTION: Execute a script to receive push in simplified
                        form via stdin. The first line of stdin will be the
                        title, and subsequent lines will be the body. Your
                        script can write lines back to stdout to send a single
                        push back. The first line of stdout will be the title,
                        and subsequent lines will be the body.
  -p EXEC_PYTHON [EXEC_PYTHON ...], --exec-python EXEC_PYTHON [EXEC_PYTHON ...]
                        ACTION: Load the given python file and execute it by
                        calling its on_push(p, pb) function with 2 arguments:
                        the push that was received and a live/connected
                        AsyncPushbullet object with which responses may be
                        sent.
  -t TIMEOUT, --timeout TIMEOUT
                        Timeout in seconds to use for actions being called
                        (default 30).
  --throttle-count THROTTLE_COUNT
                        Pushes will be throttled to this many pushes (default
                        10) in a certain number of seconds (default 10)
  --throttle-seconds THROTTLE_SECONDS
                        Pushes will be throttled to a certain number of pushes
                        (default 10) in this many seconds (default 10)
  -d DEVICE, --device DEVICE
                        Only listen for pushes targeted at given device name
  --list-devices        List registered device names
  --proxy PROXY         Optional web proxy
  --debug               Turn on debug logging
  -v, --verbose         Turn on verbose logging (INFO messages)
  -q, --quiet           Suppress all output
  --oauth2              Register your command line tool using OAuth2
  --clear-oauth2        Clears/unregisters the oauth2 token
  --version             show program's version number and exit

"""
import argparse
import asyncio
import importlib.util
import json
import logging
import math
import os
import pprint
import sys
import textwrap
import threading
import time
import traceback
import types
from functools import partial
from typing import List

from asyncpushbullet import AsyncPushbullet, __version__
from asyncpushbullet import InvalidKeyError, PushbulletError
from asyncpushbullet import LiveStreamListener
from asyncpushbullet import errors
from asyncpushbullet import oauth2

__author__ = "Robert Harder"
__email__ = "rob@iHarder.net"

DEFAULT_THROTTLE_COUNT = 10
DEFAULT_THROTTLE_SECONDS = 10
DEFAULT_COMMAND_TIMEOUT = 30
ENCODING = "utf-8"
LOG = logging.getLogger(__name__)


def main():
    # sys.argv.append("--clear-oauth2")
    # sys.argv.append("--oauth2")
    # sys.argv.append("--version")
    # sys.argv.append("-h")
    # sys.argv.append("-v")
    # sys.argv.append("--debug")
    # sys.argv += ["-k", "badkey"]
    # sys.argv += ["--key-file", "../api_key.txt"]
    # sys.argv += ["--device", "Kanga"]
    # sys.argv += ["--timeout", "3"]
    # sys.argv.append("--echo")
    # sys.argv += ["--proxy", "foo"]
    # sys.argv.append("--list-devices")
    # sys.argv += ["--exec-simple", r"C:\windows\System32\clip.exe"]
    # sys.argv += ["--exec", r"C:\windows\System32\notepad.exe"]
    # sys.argv += ["--exec-python", r"../examples/exec_python_example.py"]
    # sys.argv += ["--exec-python", r"../examples/exec_python_imagesnap.py"]
    # oauth2.PREFS.set(oauth2.OAUTH2_TOKEN_KEY, None)

    args = parse_args()
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
        traceback.print_tb(sys.exc_info()[2])
        exit_code = errors.__ERR_UNKNOWN__
    finally:
        return exit_code or errors.__EXIT_NO_ERROR__


async def _run(args):
    # Logging levels
    if args.debug:  # Debug?
        print("Log level: DEBUG")
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose:  # Verbose?
        print("Log level: INFO")
        logging.basicConfig(level=logging.INFO)

    # Clear the oauth2 token?
    if args.clear_oauth2:
        oauth2.clear_oauth2_key()
        print("Successfully cleared/unregistered the oauth2 token.")
        print("The asyncpushbullet command line tools no longer have access to your pushbullet account.")
        sys.exit(errors.__EXIT_NO_ERROR__)

    # Request setting up oauth2 access?
    if args.oauth2:
        token = await oauth2.async_gain_oauth2_access()
        if token:
            print("Successfully authenticated using OAuth2.")
            print("You should now be able to use the command line tools without specifying an API key.")
            sys.exit(errors.__EXIT_NO_ERROR__)
        else:
            print("There was a problem authenticating.")
            sys.exit(errors.__ERR_UNKNOWN__)

    # Find a valid API key
    api_key = try_to_find_key(args, not args.quiet)
    if api_key is None:
        print("You must specify an API key.", file=sys.stderr)
        sys.exit(errors.__ERR_API_KEY_NOT_GIVEN__)

    # Proxy
    proxy = lambda: args.proxy or os.environ.get("https_proxy") or os.environ.get("http_proxy")

    # List devices?
    if args.list_devices:
        print("Devices:")
        try:
            _proxy = proxy() if callable(proxy) else proxy

            async with AsyncPushbullet(api_key, proxy=_proxy) as pb:
                async for dev in pb.devices_asynciter():
                    print("\t", dev.nickname)

        except InvalidKeyError as exc:
            print(exc, file=sys.stderr)
            return errors.__ERR_INVALID_API_KEY__
        except PushbulletError as exc:
            print(exc, file=sys.stderr)
            return errors.__ERR_CONNECTING_TO_PB__
        else:
            # sys.exit(0)
            return errors.__EXIT_NO_ERROR__

    # Throttle
    throttle_count = args.throttle_count
    throttle_seconds = args.throttle_seconds

    # Device
    device = args.device

    # Timeout
    timeout = DEFAULT_COMMAND_TIMEOUT
    if args.timeout:
        timeout = float(args.timeout)

    # Create ListenApp
    listen_app = ListenApp(api_key,
                           proxy=proxy,
                           throttle_count=throttle_count,
                           throttle_seconds=throttle_seconds,
                           device=device,
                           timeout=timeout)

    # Windows needs special event loop in order to launch processes on it
    proc_loop: asyncio.BaseEventLoop
    if sys.platform == 'win32':
        proc_loop = asyncio.ProactorEventLoop()
    else:
        proc_loop = asyncio.new_event_loop()  # Processes
        asyncio.get_child_watcher()  # Main loop

    def _thread_run(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    threading.Thread(target=partial(_thread_run, proc_loop), name="Thread-proc", daemon=True).start()

    # Add actions from command line arguments
    if args.exec:
        for cmd_opts in args.exec:
            cmd_path = cmd_opts[0]
            cmd_args = cmd_opts[1:]
            action = ExecutableAction(cmd_path, cmd_args, loop=proc_loop, timeout=timeout)
            listen_app.add_action(action)

    # Add actions from command line arguments
    if args.exec_simple:
        for cmd_opts in args.exec_simple:
            cmd_path = cmd_opts[0]
            cmd_args = cmd_opts[1:]
            action = ExecutableActionSimplified(cmd_path, cmd_args, loop=proc_loop, timeout=timeout)
            listen_app.add_action(action)

    # Add actions from command line arguments
    if args.exec_python:
        for cmd_opts in args.exec_python:
            cmd_path = cmd_opts[0]
            action = ExecutableActionPython(cmd_path)
            listen_app.add_action(action)

    # Echo
    if args.echo:
        listen_app.add_action(EchoAction())

    # Default action if none specified
    if not listen_app._actions:
        print("No actions specified -- defaulting to Echo.")
        listen_app.add_action(EchoAction())

    exit_code: int = None
    try:
        exit_code = await listen_app.run()
    except KeyboardInterrupt:
        print("Caught keyboard interrupt")
    finally:
        await listen_app.close()
        if exit_code is None:
            exit_code = errors.__EXIT_NO_ERROR__
        return exit_code
        # END OF PROGRAM


def try_to_find_key(args, verbose: bool = False):
    api_key = oauth2.get_oauth2_key()  # Try this first
    if api_key:
        if verbose:
            print("Found saved oauth2 key.")

    if not api_key and "PUSHBULLET_API_KEY" in os.environ:
        api_key = os.environ["PUSHBULLET_API_KEY"].strip()
        if verbose:
            print("Found key in PUSHBULLET_API_KEY environment variable.")

    if args.key:
        api_key = args.key.strip()
        if verbose:
            print("Found key given on command line.")

    if args.key_file:
        with open(args.key_file) as f:
            api_key = f.read().strip()
        if verbose:
            print("Found key in key file", args.key_file)

    return api_key


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
    parser.add_argument("-p", "--exec-python", nargs="+", action="append",
                        help=textwrap.dedent("""
                        ACTION: Load the given python file and execute it by calling
                        its on_push(p, pb) function with 2 arguments: the push that was
                        received and a live/connected AsyncPushbullet object with which
                        responses may be sent.
                        """))
    parser.add_argument("-t", "--timeout", help="Timeout in seconds to use for actions being called (default {})."
                        .format(DEFAULT_COMMAND_TIMEOUT))
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
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress all output")
    parser.add_argument("--oauth2", action="store_true", help="Register your command line tool using OAuth2")
    parser.add_argument("--clear-oauth2", action="store_true", help="Clears/unregisters the oauth2 token")
    parser.add_argument("--version", action="version", version='%(prog)s ' + __version__)

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(errors.__ERR_NOTHING_TO_DO__)

    return args


class Action:
    """ Base class for actions that this listener will take upon receiving new pushes. """

    def __init__(self):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

    async def on_push(self, push: dict, pb: AsyncPushbullet):
        pass

    def __repr__(self):
        return type(self).__name__


class EchoAction(Action):
    """ Echoes pushes in json format to standard out. """

    async def on_push(self, push: dict, pb: AsyncPushbullet):
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

    def __init__(self, path_to_executable, args_for_exec=(), loop: asyncio.BaseEventLoop = None, timeout=None):
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

    async def on_push(self, push: dict, pb: AsyncPushbullet):
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
                except asyncio.futures.TimeoutError:
                    err_msg = "Execution timed out after {} seconds. {}".format(self.timeout, repr(self))
                    self.log.error(err_msg)
                    await pb.async_push_note(title="AsyncPushbullet Error", body=err_msg)
                    proc.terminate()

                else:
                    # Handle the response from the subprocess
                    # This goes back on the io_loop since it may involve
                    # responding to pushbullet.
                    if stdout_data == b'' and stderr_data == b'':
                        self.log.info("Nothing was returned from executable {}".format(
                            [self.path_to_executable, *self.args_for_exec]))
                    asyncio.run_coroutine_threadsafe(
                        self.handle_process_response(stdout_data, stderr_data, pb),
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

    async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes, pb: AsyncPushbullet):

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
            title = "AsyncPushbullet Error"
            body = "Stderr: {}\nStdout: {}".format(stderr_txt, stdout_txt)
            # await app.respond(title=title, body=body)
            await pb.async_push_note(title=title, body=body)
            del title, body

        elif stdout_txt is not None:
            # See if we got a structured response with JSON data
            try:
                response = json.loads(stdout_txt)
            except json.decoder.JSONDecodeError:
                # Not json, just respond with a simple push
                title = "AsyncPushbullet Response"
                body = stdout_txt
                # await app.respond(title=title, body=body)
                await pb.async_push_note(title=title, body=body)
                del title, body

            else:

                async def _hndl_resp(_resp):
                    # Interpret structures response
                    title = _resp.get("title")
                    body = _resp.get("body")

                    if _resp.get("type") == "file":
                        file_type = _resp.get("file_type")
                        file_url = _resp.get("file_url")
                        file_name = _resp.get("file_name")
                        await pb.async_push_file(file_name=file_name,
                                                 file_url=file_url,
                                                 file_type=file_type,
                                                 title=title,
                                                 body=body)
                    else:
                        await pb.async_push_note(title=title, body=body)
                    del title, body

                if type(response) == list:
                    for resp in response:
                        await _hndl_resp(resp)
                elif type(response) == dict:
                    await _hndl_resp(response)
                else:
                    # Not sure what was returned
                    await pb.async_push_note(title="Response", body=str(response))
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

    async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes, pb: AsyncPushbullet):

        if stdout_data != b"":
            data = stdout_data.decode(ENCODING, "replace")
            lines = data.splitlines()
            if len(lines) > 0:
                title = lines.pop(0).rstrip()
                body_lines = [line.rstrip() for line in lines]
                body = "\n".join(body_lines)
                resp = {"title": title, "body": body}
                stdout_data = json.dumps(resp).encode(ENCODING)

        await super().handle_process_response(stdout_data=stdout_data, stderr_data=stderr_data, pb=pb)


class ExecutableActionPython(Action):
    """
    Loads a python file and executes the on_push function.

    async def on_push(push:dict, pb:AsyncPushbullet):
        ...

    """

    def __init__(self, path: str):
        super().__init__()
        self.path = path  # type: str
        self._mod_cache = None
        self._mod_path_last_timestamp = 0.0  # type: float
        self.module_prefix = "{}_{}".format(self.__class__.__name__, id(self))  # type: str

    def __repr__(self):
        return super().__repr__() + "({})".format(self.path)

    @property
    def module(self):
        mtime = os.stat(self.path).st_mtime
        mcache = self._mod_path_last_timestamp
        if mtime > mcache and not math.isclose(mtime, mcache):
            self.log.debug("Timestamp {} for file {} is newer than cached {}.  Reloading."
                           .format(mtime, self.path, mcache))
            self._mod_path_last_timestamp = mtime
            self._mod_cache = None

        if self._mod_cache is None:
            spec = importlib.util.spec_from_file_location(self.module_prefix, self.path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._mod_cache = module
        return self._mod_cache

    async def on_push(self, push: dict, pb: AsyncPushbullet):
        return await self.module.on_push(push, pb)


class ListenApp:
    def __init__(self, api_key: str,
                 proxy=None,
                 throttle_count: int = DEFAULT_THROTTLE_COUNT,
                 throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
                 device: str = None,
                 timeout: float = None):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        # Passed arguments
        self.api_key = api_key
        self.proxy = proxy  # string or Callable
        self.throttle_max_count = throttle_count
        self.throttle_max_seconds = throttle_seconds
        self.device_name = device
        self.action_timeout = timeout

        # Internal maintenance
        self._account = None  # type: AsyncPushbullet
        self._wrapped_account = None  # type: AsyncPushbullet
        self._listener = None  # type: LiveStreamListener
        self._throttle_timestamps = []  # type: List[float]
        self._actions = []  # type: List[Action]
        self._sent_push_idens = []  # type: List[str]
        self.persistent_connection = True
        self.persistent_connection_wait_interval = 10  # seconds between retry

    @property
    def account(self):
        return self.wrapped_account

    @property
    def wrapped_account(self):
        if self._wrapped_account is None:
            acct = self._account

            async def _new(zelf, *kargs, **kwargs):
                resp = await zelf.__orig_async_push(*kargs, **kwargs)
                if resp and "iden" in resp:
                    self._sent_push_idens.append(resp.get("iden"))

            acct.__orig_async_push = acct._async_push
            acct._async_push = types.MethodType(_new, acct)
            self._wrapped_account = acct

        return self._wrapped_account

    def add_action(self, action: Action):
        self._actions.append(action)
        self.log.info("Action added: {}".format(repr(action)))

    async def close(self):
        if self._listener is not None:
            await self._listener.close()

        if self._account is not None:
            await self._account.async_close()

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

    async def run(self):
        exit_code = 0
        while self.persistent_connection:
            try:
                # Live update the proxy setting
                _proxy = self.proxy() if callable(self.proxy) else self.proxy
                if _proxy:
                    self.log.info("Proxy: {}".format(_proxy))

                print("Connecting to pushbullet...", end="", flush=True)
                async with AsyncPushbullet(api_key=self.api_key, proxy=_proxy) as pb:
                    self._account = pb

                    # If filtering on device, find or create device with that name
                    if self.device_name is not None:
                        dev = await pb.async_get_device(nickname=self.device_name)
                        if dev is None:
                            dev = await pb.async_new_device(nickname=self.device_name)
                            if dev is None:
                                self.log.error("Device {} was not found and could not be created.")
                            else:
                                self.log.info("Device {} was not found, so we created it.".format(self.device_name))

                    async with LiveStreamListener(pb, only_this_device_nickname=self.device_name) as lsl:
                        print("Connected.", flush=True)
                        self.log.info("Connected to Pushbullet websocket.")
                        self._listener = lsl

                        if self.device_name is None:
                            print("Awaiting pushes...")
                        else:
                            print("Awaiting pushes to device {}...".format(self.device_name))

                        async for push in lsl:
                            self.log.info("Received push (title={}, body={}) {}"
                                          .format(push.get("title"), push.get("body"), push))
                            print("Received push (title={}, body={})"
                                  .format(push.get("title"), push.get("body")))

                            await self._throttle()

                            if push.get("iden") in self._sent_push_idens:
                                # This is one we sent - ignore it
                                self.log.debug(
                                    "Ignoring an incoming push that we sent. (iden={})".format(push.get('iden')))
                                continue

                            async def _call_on_push(_action: Action):
                                self.log.info("Calling action {}".format(repr(_action)))
                                try:
                                    await asyncio.wait_for(_action.on_push(push, self.wrapped_account),
                                                           timeout=self.action_timeout)
                                    await asyncio.sleep(0)

                                except asyncio.TimeoutError as te:
                                    err_msg = "Action {} timed out after {}+ seconds".format(_action,
                                                                                             self.action_timeout)
                                    await pb.async_push_note(title="AsyncPushbullet Error", body=err_msg)
                                    if not self.log.isEnabledFor(logging.DEBUG):
                                        err_msg += " (turn on --debug to see traceback)"
                                    self.log.warning(err_msg)
                                    if self.log.isEnabledFor(logging.DEBUG):
                                        traceback.print_tb(sys.exc_info()[2])
                                    del err_msg

                                except Exception as ex:
                                    err_msg = "Action {} caused exception {}".format(_action, ex)
                                    await pb.async_push_note(title="AsyncPushbullet Error", body=err_msg)
                                    if not self.log.isEnabledFor(logging.DEBUG):
                                        err_msg += " (turn on --debug to see traceback)"
                                    self.log.warning(err_msg)
                                    if self.log.isEnabledFor(logging.DEBUG):
                                        traceback.print_tb(sys.exc_info()[2])
                                    del err_msg

                                finally:
                                    self.log.debug("Leaving action {}".format(repr(_action)))

                            for a in self._actions:
                                asyncio.get_event_loop().create_task(_call_on_push(a))


            except InvalidKeyError as ex:
                print(flush=True)
                exit_code = errors.__ERR_INVALID_API_KEY__
                self.log.warning(ex)
                self.persistent_connection = False  # Invalid key results in immediate exit

            except Exception as ex:
                print(flush=True)
                err_msg = "{}: {}".format(ex.__class__.__name__, ex)
                if not self.log.isEnabledFor(logging.DEBUG):
                    err_msg += " (turn on --debug to see traceback)"
                self.log.warning(err_msg)
                if self.log.isEnabledFor(logging.DEBUG):
                    traceback.print_tb(sys.exc_info()[2])
                exit_code = errors.__ERR_UNKNOWN__  # exit code

            else:
                print("Connection closed.")

            finally:
                if self.persistent_connection:
                    print("Waiting {} seconds to try again...".format(self.persistent_connection_wait_interval),
                          flush=True)
                    await asyncio.sleep(self.persistent_connection_wait_interval)

        return exit_code


if __name__ == "__main__":
    main()
