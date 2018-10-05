#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Horribly dangerous.  Do not use.
"""
import asyncio
import os
import sys
import traceback
from collections import namedtuple
from typing import List, AsyncIterator

# import asyncpushbullet  # pip install asyncpushbullet
from async_command import AsyncReadConsole, async_execute_command
from asyncpushbullet import AsyncPushbullet, EphemeralComm, oauth2  # pip install asyncpushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"
__license__ = "Public Domain"

PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")
# asyncpushbullet.oauth2.gain_oauth2_access()

CMsg = namedtuple("console", ["from_stdout", "from_stderr", "for_stdin", "status"],
                  defaults=([], [], [], None))


def main():
    # An example
    loop = asyncio.get_event_loop()

    sys.argv.append("console")
    sys.argv.append("server")

    if "server" in sys.argv and "console" in sys.argv:
        if sys.platform == 'win32':
            cmd = "cmd"
        else:
            cmd = "bash"
        t1 = loop.create_task(run_console())
        t2 = loop.create_task(run_cmd_server(cmd))
        loop.run_until_complete(asyncio.gather(t1, t2))
        loop.run_until_complete(asyncio.sleep(1))
        print("both closed")
        return

    if sys.argv[-1] == "console":
        loop.run_until_complete(run_console())

    if sys.argv[-1] == "server":
        loop.run_until_complete(run_cmd_server("dir"))


async def run_console():
    # Read console input from input() and write to pushbullet
    # Echo pushbullet from_stdout through print()
    print("Starting console for connecting with remote server", flush=True)
    stdout_task = None  # type: asyncio.Task
    try:
        key = oauth2.get_oauth2_key()

        async with AsyncPushbullet(key, proxy=PROXY) as pb:
            async with EphemeralComm(pb, CMsg) as ec:  # type: EphemeralComm[CMsg]
                # msg = {"type": "console", "status": "Console input connected to pushbullet"}
                # await pb.async_push_ephemeral(msg)
                kmsg = CMsg(status="Console input connected to pushbullet")
                await ec.send(kmsg)

                async with AsyncReadConsole("cmd input: ") as arc:
                    async def _dump_stdout():
                        try:
                            remote_stdout_closed = False
                            remote_stderr_closed = False
                            async for kmsg in ec.with_timeout(10, break_on_timeout=False):

                                if kmsg is None:
                                    # print("TIMEDOUT")
                                    if remote_stderr_closed or remote_stdout_closed:
                                        # We received a close from one but not the other.  Just quit.
                                        print("Remote command exited.", flush=True)
                                        await ec.close()  # TODO: error here
                                        # break
                                    continue

                                for line in kmsg.from_stdout:
                                    if line is None:
                                        # print("stdout closed.")
                                        remote_stdout_closed = True
                                    else:
                                        print(line, flush=True)

                                for line in kmsg.from_stderr:
                                    if line is None:
                                        # print("stderr closed.")
                                        remote_stderr_closed = True
                                    else:
                                        print(line, file=sys.stderr, flush=True)

                                if remote_stdout_closed and remote_stderr_closed:
                                    print("Remote command exited.", flush=True)
                                    await ec.close()
                            # print("end: async for kmsg in ec")

                        except Exception as ex:
                            print("ERROR in _dump_stdout:", ex, file=sys.stderr, flush=True)
                            traceback.print_tb(sys.exc_info()[2])
                        finally:
                            print('FINALLY: closing arc')
                            await arc.close()
                            print("arc.close() returned")

                    stdout_task = asyncio.get_event_loop().create_task(_dump_stdout())

                    async for line in arc:
                        if line is None:
                            assert line is not None, "This should never happen"
                            break
                        else:
                            # msg = {"type": "console", "for_stdin": line}
                            # await pb.async_push_ephemeral(msg)
                            # print("Sending command: " + line)
                            kmsg = CMsg(for_stdin=[line])
                            await ec.send(kmsg)
                    print("exited async for line in arc:")

    except Exception as ex:
        print("ERROR in run_console:", ex, file=sys.stderr, flush=True)
        traceback.print_tb(sys.exc_info()[2])
    finally:
        print("Console tool closing ... ", end="", flush=True)
        if stdout_task:
            stdout_task.cancel()
        print("Closed.", flush=True)


class LiveStreamCommandListener:
    def __init__(self, ec):
        self.ec: EphemeralComm[CMsg] = ec
        self.lines: List[str] = []

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    async def __anext__(self) -> str:
        ec_iter = self.ec.__aiter__()
        while len(self.lines) == 0:
            kmsg = await ec_iter.__anext__()
            self.lines += kmsg.for_stdin
        line = self.lines.pop(0)
        print(f"Received command: {line}")
        return line


async def run_cmd_server(cmd, args: List = None):
    print("Remote command server.", flush=True)
    loop = asyncio.get_event_loop()
    args = args or []

    try:
        key = oauth2.get_oauth2_key()

        async with AsyncPushbullet(key, proxy=PROXY) as pb:
            stdout_queue = asyncio.Queue()
            stderr_queue = asyncio.Queue()
            async with EphemeralComm(pb, CMsg) as ec:  # type: EphemeralComm[CMsg]

                # msg = {"type": "console", "status": "command server connected to pushbullet"}
                # await pb.async_push_ephemeral(msg)
                kmsg = CMsg(status="command server connected to pushbullet")
                await ec.send(kmsg)

                async def _output_flusher(_q, name):
                    # name is from_stdout or from_stderr
                    while True:
                        lines = []
                        while len(lines) < 20:
                            line: bytes
                            try:
                                if lines:
                                    # If we have something to send, wait only a moment
                                    # to see if there's anything else coming.
                                    # print("Waiting with timeout", name)
                                    line = await asyncio.wait_for(_q.get(), timeout=0.25)
                                else:
                                    # print("Waiting without timeout", name)
                                    # If we have an empty queue, no need for the timeout
                                    line = await _q.get()

                            except asyncio.TimeoutError:
                                # print("TE")
                                break
                                # break  # while loop for length of lines
                            else:
                                # print(f"{name}: {line}")
                                if line is None:
                                    # print(f"{name} output flusher on server done!")
                                    # return  # We're done!
                                    lines.append(None)
                                    break
                                else:
                                    line = line.decode().rstrip()
                                    lines.append(line)

                        # print(f"{name} server LINES:", lines)
                        if lines:
                            try:
                                # msg = {"type": "console", name: lines}
                                # await pb.async_push_ephemeral(msg)
                                if name == "from_stdout":
                                    kmsg = CMsg(from_stdout=lines)
                                    await ec.send(kmsg)
                                elif name == "from_stderr":
                                    kmsg = CMsg(from_stderr=lines)
                                    await ec.send(kmsg)

                                if lines[-1] is None:
                                    # print(f"{name} found None - output flusher is returning")
                                    return  # We're done
                            except Exception as ex:
                                print("ERROR:", ex, file=sys.stderr, flush=True)
                                traceback.print_tb(sys.exc_info()[2])

                t1 = loop.create_task(_output_flusher(stdout_queue, "from_stdout"))
                t2 = loop.create_task(_output_flusher(stderr_queue, "from_stderr"))

                # async with LiveStreamListener(pb, types="ephemeral:console") as lsl:

                await async_execute_command(cmd, args,
                                            provide_stdin=LiveStreamCommandListener(ec),
                                            handle_stderr=stderr_queue.put,
                                            # handle_stdout=print)
                                            handle_stdout=stdout_queue.put)

                # print("ADDING None TO BOTH OUTPUT QUEUES")
                await stdout_queue.put(None)  # mark that we're done for the output flushers
                await stderr_queue.put(None)  # mark that we're done

                await asyncio.gather(t1, t2)

        # print("SERVER asyncpush WITH BLOCK EXITED")


    except Exception as ex:
        print("ERROR:", ex, file=sys.stderr, flush=True)
        traceback.print_tb(sys.exc_info()[2])

    finally:
        print("Server tool closing ... ", end="", flush=True)
        print("Closed.", flush=True)


if __name__ == "__main__":
    main()
