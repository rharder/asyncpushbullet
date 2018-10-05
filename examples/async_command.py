#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tools for running command line processes compatibly with asyncio.
"""
import asyncio
import datetime
import logging
import pprint
import queue
import sys
import threading
import time
import traceback
import weakref
from functools import partial
from typing import Callable, AsyncIterator, Iterable, Union

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"
__license__ = "Public Domain"


def main():
    # An example
    loop = asyncio.get_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test())
    loop.run_until_complete(
        async_execute_command("cmd",
                              provide_stdin=AsyncReadConsole(),
                              handle_stdout=lambda x: print(f"{x.decode() if x else ''}", end="", flush=True),
                              handle_stderr=lambda x: print(f"{x.decode() if x else ''}", end="", file=sys.stderr,
                                                            flush=True)
                              )
    )


async def test():
    print("This will test the awaitiness.")

    async def _heartbeat():
        for _ in range(3):
            print("♡", flush=True)
            await asyncio.sleep(2)

    asyncio.create_task(_heartbeat())

    async with AsyncReadConsole() as arc:
        resp = await arc.input("Say: ")
        print(f"you said '{resp}'")

    print("The prompt can be a function that updates each time it is displayed.")
    async with AsyncReadConsole(
            prompt=lambda: "{}: ".format(datetime.datetime.now()),
            end=lambda x: f" ({len(x)})") \
            as arc:
        async for line in arc:
            print(f"GOT: [{line}]", flush=True)
            if line.startswith("EOF"):
                break


class AsyncReadConsole:
    """An AsyncIterator that reads from the console."""

    def __init__(self, prompt: Union[str, Callable] = None, end: Union[str, Callable] = None):
        """Creates a new AsyncReadConsole with optional default prompt.

        The prompt can be a Callable function/lambda or a string or None.
        If prompt is Callable, it will be called each time the prompt is
        presented, making it possible to have "live" prompts.  The prompt
        can be a regular or async function.

        The end parameter can be a callable function/lambda or a string or None.
        If callable it can be either a coroutine or a regular function.
        The line that is about to be sent is passed as an argument.

        :param prompt: optional prompt
        :param end: end character of a line, default is no end marker
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.main_loop: asyncio.BaseEventLoop = None
        self.thread_loop: asyncio.BaseEventLoop = None

        self.thread: threading.Thread = None
        self.arc_stopping: bool = False
        self.arc_stopping_evt: asyncio.Event = None
        self.thread_stopped: asyncio.Event = None
        self.self_started: bool = None

        self.end: Union[str, Callable] = end  # "\n" if end is None else end
        self.prompt: Union[str, Callable] = prompt
        self.prompt_queue: asyncio.Queue = None  # on thread loop
        self.input_queue: asyncio.Queue = None  # on main loop

    def __del__(self):
        print(f"__del__, prompt_queue: {self.prompt_queue.qsize()}", flush=True)
        while True:
            try:
                x = self.prompt_queue.get_nowait()
                print(f"\t{x}", flush=True)
            except asyncio.QueueEmpty:
                break

        print(f"__del__, input_queue: {self.input_queue.qsize()}", flush=True)
        while True:
            try:
                x = self.input_queue.get_nowait()
                print(f"\t{x}", flush=True)
            except asyncio.QueueEmpty:
                break


    async def __aenter__(self):
        # print("__aenter__", flush=True)
        self.main_loop = asyncio.get_event_loop()
        self.input_queue = asyncio.Queue()
        _thread_ready_to_go = asyncio.Event()
        self.thread_stopped = asyncio.Event()
        self.arc_stopping_evt = asyncio.Event()

        def _thread_run():
            # print("_thread_run", flush=True)
            self.thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.thread_loop)

            async def _async_thread_run():
                # print("_async_thread_run", flush=True)
                try:
                    self.prompt_queue = asyncio.Queue()
                    self.main_loop.call_soon_threadsafe(_thread_ready_to_go.set)  # Thread is up and running

                    while not self.arc_stopping:
                        # Do not proceed until someone actually wants a line of input
                        # because once the input() function is called, we're blocked there.
                        print(f"AWAITING prompt_queue.get()",flush=True)
                        prompt = await self.prompt_queue.get()
                        print(f"GOT PROMPT: '{prompt}'", flush=True)
                        await asyncio.sleep(0)
                        if self.arc_stopping:
                            print("STOPPING, SEND None TO INPUT_QUEUE", flush=True)
                            asyncio.run_coroutine_threadsafe(self.input_queue.put(None), self.main_loop)
                            break
                        line = None
                        try:
                            print("LISTENING FOR STDIN INPUT...",flush=True)
                            if prompt:
                                line = input(prompt)
                            else:
                                line = input()

                        except EOFError as ex:
                            print(f"EOFError {ex}", flush=True)
                            asyncio.run_coroutine_threadsafe(self.input_queue.put(ex), self.main_loop)
                            break

                        else:
                            print(f"ADD LINE TO INPUT QUEUE: {line}",flush=True)
                            asyncio.run_coroutine_threadsafe(self.input_queue.put(line), self.main_loop)
                        finally:
                            print("DONE WITH THIS ROUND OF INPUT")

                        # assert line is not None, "Did not expect line to be none"
                        if line is None:
                            print("DID NOT EXPECT THIS", flush=True)
                            break
                        print("LAST LINE WHILE LOOP", flush=True)
                    # await asyncio.sleep(0)  # one last time to yield to event loop
                    self.thread_loop = None
                except Exception as ex:
                    print("Error in _async_thread_run:", ex.__class__.__name__, ex, file=sys.stderr, flush=True)
                    traceback.print_tb(sys.exc_info()[2])
                finally:
                    print("thread loop exiting")


            self.thread_loop.run_until_complete(_async_thread_run())
            print("_async_thread_run is complete")
            self.main_loop.call_soon_threadsafe(self.thread_stopped.set)
            print("_thread_run exiting")

        if self.thread_loop is None:
            self.thread = threading.Thread(target=_thread_run, name="Thread-console_input", daemon=True)
            self.thread.start()
        else:
            raise Exception(f"{self.__class__.__name__} already has a support thread--was __aenter__ called twice?")

        await _thread_ready_to_go.wait()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print("__aexit__", flush=True)
        if self.arc_stopping:
            print("Already stopping", flush=True)
            pass
        else:
            self.arc_stopping = True
            self.arc_stopping_evt.set()
            await self.input_queue.put(None)
            if self.thread_loop is not None:
                print("PUTTING ONE LAST NONE", flush=True)
                asyncio.run_coroutine_threadsafe(self.prompt_queue.put(None), self.thread_loop)
        return

    def __aiter__(self) -> AsyncIterator[str]:
        # print("__aiter__", flush=True)
        return self

    async def __anext__(self, prompt=None, end=None) -> str:
        try:
            print("__anext__", flush=True)
            if self.arc_stopping:
                raise StopAsyncIteration()

            if self.main_loop is None:  # Apparently __aenter__ was never called
                _self_start_ready = asyncio.Event()

                async def _self_start():
                    async with self as _:
                        self.self_started = True
                        _self_start_ready.set()
                        await self.arc_stopping_evt.wait()

                asyncio.create_task(_self_start())
                await _self_start_ready.wait()

            # Resolve prompt
            prompt = prompt or self.prompt
            if asyncio.iscoroutinefunction(prompt):
                prompt = await prompt()
            elif callable(prompt):
                prompt = prompt()

            print(f"__anext__ is putting a prompt on the queue: '{prompt}' ...", flush=True)
            asyncio.run_coroutine_threadsafe(self.prompt_queue.put(prompt), self.thread_loop)
            print(f"__anext__ is awaiting the input queue...", flush=True)
            line = await self.input_queue.get()
            print(f"__anext__ got something from the input queue: '{line}'", flush=True)

            if isinstance(line, Exception):
                raise StopAsyncIteration(line) from line
            if line is None:
                print("LINE IS NONE, RAISING StopAsyncIteration", flush=True)
                raise StopAsyncIteration()
            else:
                # Resolve ending
                end = self.end if end is None else end
                if asyncio.iscoroutinefunction(end):
                    end = await end(line)
                elif callable(end):
                    end = end(line)
                if end is not None:
                    line = f"{line}{end}"
                return line

        except StopAsyncIteration as sai:
            if self.self_started:
                await self.close()
            raise sai

    async def input(self, prompt=None, end=None):
        line = None
        try:
            line = await self.__anext__(prompt=prompt, end=end)
        except StopAsyncIteration:
            line = None
        finally:
            return line

    async def readline(self):
        """Reads a line of input.  Same as input() but without a prompt."""
        return await self.input()

    async def close(self):
        # print(self.__class__.__name__, "close() entrance", flush=True)
        self.arc_stopping = True
        self.arc_stopping_evt.set()
        await self.input_queue.put(None)
        if self.thread_loop:
            asyncio.run_coroutine_threadsafe(self.prompt_queue.put(None), self.thread_loop)
        print("WAITING FOR self.thread_stopped.wait()", flush=True)
        await self.thread_stopped.wait()
        print("ZZZ", self.__class__.__name__, "close() exit", flush=True)


async def async_execute_command(cmd, args: Iterable = (),
                                provide_stdin: AsyncIterator = None,
                                handle_stdout: Callable = None,
                                handle_stderr: Callable = None, daemon=True):
    parent_loop = asyncio.get_event_loop()
    parent_loop_tasks = weakref.WeakSet()
    thread_done_evt = asyncio.Event()
    output_callback_queue = asyncio.Queue()

    async def _monitor_output_callback_queue():
        while True:
            try:
                x = await output_callback_queue.get()
                if x is None:
                    # We're all done -- shutdown
                    break
                check = x.func if isinstance(x, partial) else x
                if asyncio.iscoroutinefunction(check):
                    await x()
                else:
                    x()
            except Exception as ex:
                print("Error in callback:", ex.__class__.__name__, ex, file=sys.stderr, flush=True)
                traceback.print_tb(sys.exc_info()[2])
        # print("DONE: _monitor_callback_queue", flush=True)

    parent_loop_tasks.add(asyncio.create_task(_monitor_output_callback_queue()))

    if sys.platform == 'win32':
        proc_loop = asyncio.ProactorEventLoop()
    else:
        proc_loop = asyncio.new_event_loop()  # Processes
        asyncio.get_child_watcher()  # Main loop

    def _thread_run(_thread_loop: asyncio.BaseEventLoop):
        # Running on thread that will host proc_loop

        async def __run():
            # Running within proc_loop
            # asyncio.get_event_loop().set_debug(True)

            try:
                # print("Server is launching", cmd, *args, flush=True)
                proc = await asyncio.create_subprocess_exec(
                    cmd, *args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)

                async def __process_output(_out: asyncio.StreamReader, _output_callback: Callable):
                    # Runs within proc_loop
                    try:
                        while True:
                            buf = b''
                            line = None
                            while line is None:
                                try:
                                    # Handle an incomplete line output such as when
                                    # a command prompt leaves the input cursor at the end.
                                    c = await asyncio.wait_for(_out.read(1), 0.1)
                                except asyncio.futures.TimeoutError:
                                    if buf:
                                        line = buf
                                # except Exception as ex:
                                #     print("Exception", type(ex), ex, file=sys.stderr, flush=True)
                                #     pass
                                else:
                                    buf += c
                                    if c == b'\n':
                                        line = buf

                                    # Handle EOF
                                    elif c == b'':
                                        line = buf
                                        if line:
                                            # First send whatever line we have left
                                            part = partial(_output_callback, line)
                                            asyncio.run_coroutine_threadsafe(output_callback_queue.put(part),
                                                                             parent_loop)
                                        # Then send a marker saying we're done
                                        part = partial(_output_callback, None)
                                        asyncio.run_coroutine_threadsafe(output_callback_queue.put(part), parent_loop)
                                        return

                            if line:
                                part = partial(_output_callback, line)
                                asyncio.run_coroutine_threadsafe(output_callback_queue.put(part), parent_loop)
                            else:
                                break
                    except Exception as ex:
                        print("Error in __process_output:", ex.__class__.__name__, ex, file=sys.stderr, flush=True)
                        traceback.print_tb(sys.exc_info()[2])

                async def __receive_input(_input_provider: AsyncIterator[str]):
                    # Runs in parent_loop
                    # asyncio.get_event_loop().set_debug(True)
                    async for __line in _input_provider:
                        proc.stdin.write(f"{__line}\n".encode())

                    proc.stdin.write_eof()
                    # input_done_evt.set()

                tasks = []
                if provide_stdin:
                    asyncio.run_coroutine_threadsafe(__receive_input(provide_stdin), parent_loop)
                    # parent_loop_tasks.add(parent_loop.create_task(input_done_evt.wait()))
                if handle_stdout:
                    tasks.append(_thread_loop.create_task(__process_output(proc.stdout, handle_stdout)))
                if handle_stderr:
                    tasks.append(_thread_loop.create_task(__process_output(proc.stderr, handle_stderr)))

                # print("GATHERING...", flush=True)
                await asyncio.gather(*tasks)
                # print(f"GATHERED {pprint.pformat(tasks)}", flush=True)

            except Exception as ex:
                print(ex, file=sys.stderr, flush=True)
                traceback.print_tb(sys.exc_info()[2])

        asyncio.set_event_loop(_thread_loop)
        _thread_loop.run_until_complete(__run())
        parent_loop.call_soon_threadsafe(thread_done_evt.set)
        # parent_loop.call_soon_threadsafe(input_done_evt.set)
        print("Thread-proc run closed.", flush=True)

    # Launch process is another thread, and wait for it to complete
    threading.Thread(target=partial(_thread_run, proc_loop), name="Thread-proc", daemon=daemon).start()
    await thread_done_evt.wait()  # Waiting for proc_loop thread to finish
    await output_callback_queue.put(None)  # Signal that no more callbacks will be called
    await asyncio.gather(*parent_loop_tasks)  # Wait for all callbacks to finish

    await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
