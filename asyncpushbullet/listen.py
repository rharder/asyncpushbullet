#!/usr/bin/env python3
"""
A command line script for listening for pushes
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time

from asyncpushbullet import PushListener

sys.path.append("..")
from asyncpushbullet import AsyncPushbullet

__author__ = "Robert Harder"
__email__ = "rob@iHarder.net"
__encoding__ = "utf-8"

API_KEY = ""  # YOUR API KEY

# logging.basicConfig(level=logging.DEBUG)

# sys.argv.append("--list-devices")
# sys.argv += ["--file", __file__]
# sys.argv.append("--transfer.sh")

# sys.argv += ["--exec", "c:\\windows\\system32\\calc.exe"]
# sys.argv += ["--exec", r"c:\python35\python.exe",
#              r"C:\Users\Robert.Harder\Documents\GitHub\asyncpushbullet\asyncpushbullet\scratch.py"]


# sys.argv.append("--debug")
# sys.argv.append("--verbose")


def main():
    args = parse_args()
    do_main(args)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--key", help="Your Pushbullet.com API key")
    parser.add_argument("-e", "--echo", help="ACTION: Echo push as json to stdout (default)")
    parser.add_argument("-x", "--exec", nargs="+", action="append",
                        help="ACTION: Execute a script to receive push as json via stdin")

    parser.add_argument("-d", "--debug", action="store_true", help="Turn on debug logging")
    parser.add_argument("-v", "--verbose", action="store_true", help="Turn on verbose logging (INFO messages)")

    args = parser.parse_args()
    return args


def do_main(args):
    global API_KEY

    # Key
    if args.key:
        API_KEY = args.key
    API_KEY = API_KEY.strip()
    if API_KEY == "":
        print(
            "You must specify an API key, either at the command line or with the PUSHBULLET_API_KEY environment variable.",
            file=sys.stderr)
        sys.exit(1)

    # Verbose?
    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    # Debug?
    if args.debug:
        print("Log level: DEBUG")
        logging.basicConfig(level=logging.DEBUG)

    # Create ListenApp
    listen_app = ListenApp(API_KEY)

    # Add actions from command line arguments
    if args.exec:
        for cmd_opts in args.exec:
            cmd_path = cmd_opts[0]
            cmd_args = cmd_opts[1:]
            action = ExecutableAction(cmd_path, cmd_args)
            listen_app.add_action(action)

    # listen_app.add_action(ExecutableAction(r"c:\python35\python.exe", [
    #     r"C:\Users\Robert.Harder\Documents\GitHub\asyncpushbullet\asyncpushbullet\scratch.py"]))

    # listen_app.add_action(ExecutableActionSimplified(r"c:\python35\python.exe", [
    #     r"C:\Users\Robert.Harder\Documents\GitHub\asyncpushbullet\asyncpushbullet\scratch.py"]))

    # listen_app.add_action(ExecutableAction("c:\\windows\\system32\\calc.exe"))

    # Default action if none specified
    if len(listen_app.actions) == 0 or args.echo:
        listen_app.add_action(EchoAction())

    # Windows needs special event loop in order to launch processes on it
    if sys.platform == 'win32':
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)

    # Run loop indefinitely
    loop = asyncio.get_event_loop()

    async def _timeout():
        await asyncio.sleep(2)
        await listen_app.close()
    # loop.create_task(_timeout())


    try:
        loop.run_until_complete(listen_app.run())
    except KeyboardInterrupt as e:
        print("Caught keyboard interrupt")
    finally:
        loop.run_until_complete(listen_app.close())
    # END OF PROGRAM


class Action:
    """ Base class for actions that this listener will take upon receiving new pushes. """

    def __init__(self):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

    async def do(self, push: dict, pb: AsyncPushbullet):
        pass

    def __repr__(self):
        return type(self).__name__


class EchoAction(Action):
    """ Echoes pushes in json format to standard out. """

    async def do(self, push: dict, pb: AsyncPushbullet):
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

    def __init__(self, path_to_executable, args_for_exec=(), timeout=30):
        super().__init__()
        self.path_to_executable = path_to_executable
        self.args_for_exec = args_for_exec
        self.protocol = ExecutableAction._ProcessProtocol(self)
        self.timeout = timeout

        if not os.path.isfile(path_to_executable):
            self.log.warning("Executable not found at time launch time.  " +
                             "Will still attempt to run when pushes are received. ({})"
                             .format(path_to_executable))

    def __repr__(self):
        return "{}({} {})".format(super().__repr__(), self.path_to_executable, " ".join(self.args_for_exec))

    async def do(self, push: dict, pb: AsyncPushbullet):

        # Launch process
        try:
            proc = await asyncio.create_subprocess_exec(self.path_to_executable,
                                                        *self.args_for_exec,
                                                        stdin=asyncio.subprocess.PIPE,
                                                        stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.PIPE)
        except Exception as e:
            self.log.error("Error occurred while trying to launch script. ({}): {}"
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
                await self.handle_process_response(stdout_data, stderr_data, pb)

    async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes, pb: AsyncPushbullet):

        # Any stderr output?
        if stderr_data != b"":
            self.log.error("Error from {}: {}".format(repr(self), stderr_data))

        # Any stdout output?
        if stdout_data != b"":
            self.log.info("Response from {}: {}".format(repr(self), stdout_data))

            # Requesting a response push?
            resp = {}
            try:
                resp = json.loads(stdout_data.decode(__encoding__, "replace"))
            except json.decoder.JSONDecodeError as e:
                print(e)

            for push in resp.get("pushes", []):  # type: dict
                title = push.get("title", "no title")
                body = push.get("body", "no body")
                await pb.async_push_note(title=title, body=body)


class ExecutableActionSimplified(ExecutableAction):
    """
    Interprets subprocess response from stdout as line1 = title and remaining lines = body.

    Example response from subprocess:

        Fish Food Served
        Your automated fish feeding gadget has fed your fish.

    """

    async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes, pb: AsyncPushbullet):

        if stdout_data != b"":
            data = stdout_data.decode(__encoding__, "replace")
            lines = data.splitlines()
            if len(lines) > 0:
                title = lines.pop(0).rstrip()
                body_lines = [line.rstrip() for line in lines]
                body = "\n".join(body_lines)
                resp = {"pushes": [{"title": title, "body": body}]}
                stdout_data = json.dumps(resp).encode(__encoding__)

        await super().handle_process_response(stdout_data=stdout_data, stderr_data=stderr_data, pb=pb)


class ListenApp:
    def __init__(self, api_key: str, throttle_count: float = 10, throttle_seconds: float = 10):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.pb = AsyncPushbullet(api_key=api_key)
        self.throttle_max_count = throttle_count
        self.throttle_max_seconds = throttle_seconds
        self._throttle_timestamps = []  # type: [float]
        self.actions = []  # type: [Action]
        self._listener = None  # type: PushListener

    def add_action(self, action: Action):
        self.actions.append(action)
        self.log.info("Action added: {}".format(repr(action)))

    async def close(self):
        await self._listener.close()
        await self.pb.close()


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
            self.log.info("Throttling pushes that are coming too fast. Stalling {:0.1f} seconds ...".format(stall))
            await asyncio.sleep(stall)

    async def run(self):
        self.log.info("Awaiting pushes ...".format(str(self)))
        loop = asyncio.get_event_loop()

        self._listener = PushListener(self.pb)
        async for push in self._listener:  # type: dict
            self.log.info("Received push {}".format(push))
            await self._throttle()

            for action in self.actions:  # type: Action
                self.log.debug("Calling action {}".format(repr(action)))
                loop.create_task(action.do(push, self.pb))

        self.log.debug("run() coroutine exiting")


if __name__ == "__main__":
    if API_KEY == "":
        if "PUSHBULLET_API_KEY" in os.environ:
            API_KEY = os.environ["PUSHBULLET_API_KEY"]
        else:
            api_file = os.path.join(os.path.dirname(__file__), "../api_key.txt")
            with open(api_file) as f:
                API_KEY = f.read().strip()
    main()
