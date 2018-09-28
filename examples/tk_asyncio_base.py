#!/usr/bin/env python3
"""
A base class for Tk apps that will use asyncio.
"""
import asyncio
import queue
import sys
import threading
import tkinter as tk
import traceback
from functools import partial
from typing import Callable, Union, Coroutine

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"
__license__ = "Public Domain"


class TkAsyncioBaseApp:
    """

    """

    def __init__(self, base: tk.Misc):
        self.__tk_base: tk.Misc = base

        # Inter-thread communication
        self._ioloop: asyncio.BaseEventLoop = None
        self.__tk_queue: queue.Queue = queue.Queue()  # Functions to call on tk loop
        self.__tk_after_ids: queue.Queue = queue.Queue()  # Requests to process tk queue

        # IO Loop
        self.__create_io_loop()

    def __create_io_loop(self):
        """Creates a new thread to manage an asyncio event loop."""
        if self._ioloop is not None:
            raise Exception("An IO loop is already running.")

        _ready = threading.Event()  # Don't leave this function until thread is ready

        def _thread_run(loop: asyncio.BaseEventLoop):
            asyncio.set_event_loop(loop)
            loop.call_soon_threadsafe(_ready.set)
            loop.run_forever()

        self._ioloop: asyncio.BaseEventLoop = asyncio.new_event_loop()
        threading.Thread(target=partial(_thread_run, self._ioloop), name="Thread-asyncio", daemon=True).start()
        _ready.wait()

    async def ioloop_exception_happened(self, extype, ex, tb, func):
        """Called when there is an unhandled exception in a job that was
        scheduled on the io event loop.

        The arguments are the three standard sys.exc_info() arguments
        plus the function that was called as a scheduled job and subsequently
        raised the Exception.

        :param extype: the exception type
        :param ex: the Exception object that was raised
        :param tb: the traceback associated with the exception
        :param func: the scheduled function that caused the trouble
        """
        print("TkAsyncioBaseApp.ioloop_exception_happened called.  Override this function in your app.",
              file=sys.stderr, flush=True)
        traceback.print_tb(tb)

    def tkloop_exception_happened(self, extype, ex, tb, func):
        """Called when there is an unhandled exception in a job that was
        scheduled on the tk event loop.

        The arguments are the three standard sys.exc_info() arguments
        plus the function that was called as a scheduled job and subsequently
        raised the Exception.

        :param extype: the exception type
        :param ex: the Exception object that was raised
        :param tb: the traceback associated with the exception
        :param func: the scheduled function that caused the trouble
        """
        print("TkAsyncioBaseApp.tkloop_exception_happened was called.  Override this function in your app.",
              file=sys.stderr, flush=True)
        print("Exception:", extype, ex, func, file=sys.stderr, flush=True)
        traceback.print_tb(tb)

    def io(self, func: Union[Coroutine, Callable], *kargs, **kwargs) -> Union[asyncio.Future, asyncio.Handle]:
        """
        Schedule a coroutine or regular function to be called on the io event loop.

        self.io(some_coroutine())
        self.io(some_func, "some arg")

        The positional *kargs and named **kwargs arguments only apply when
        a non-coroutine function is passed such as:

            self.io(print, "hello world", file=sys.stderr)

        Returns a Future (for coroutines) or Handle (for regular functions) that can
        be used to cancel or otherwise inspect the scheduled job.

        This is threadsafe.

        :param func: the coroutine or function
        :param kargs: optional positional arguments for the function
        :param kwargs: optional named arguments for the function
        :return:
        """

        async def _coro_run():
            # noinspection PyBroadException
            try:
                await func
            except Exception:
                await self.ioloop_exception_happened(*sys.exc_info(), func)

        def _func_run():
            # noinspection PyBroadException
            try:
                func(*kargs, **kwargs)
            except Exception:
                self.tkloop_exception_happened(*sys.exc_info(), func)

        if asyncio.iscoroutine(func):
            return asyncio.run_coroutine_threadsafe(_coro_run(), self._ioloop)
        else:
            return self._ioloop.call_soon_threadsafe(_func_run)

    def tk(self, func: Callable, *kargs, **kwargs):
        """
        Schedule a function to be called on the Tk GUI event loop.

        This is threadsafe.

        :param func: The function to call
        :param kargs: optional positional arguments
        :param kwargs: optional named arguments
        :return:
        """

        # Put the command in a thread-safe queue and schedule the tk thread
        # to retrieve it in a few milliseconds.  The few milliseconds delay
        # helps if there's a flood of calls all at once.

        class Cancelable:
            def __init__(self, job):
                self.job = job
                self.cancelled = False

            def cancel(self):
                self.cancelled = True

        x = Cancelable(partial(func, *kargs, **kwargs))
        self.__tk_queue.put(x)

        # Now throw away old requests to process the tk queue
        while True:
            try:
                old_scheduled_timer = self.__tk_after_ids.get(block=False)
                self.__tk_base.after_cancel(old_scheduled_timer)
            except queue.Empty:
                break
        new_scheduled_timer = self.__tk_base.after(5, self._tk_process_queue)
        self.__tk_after_ids.put(new_scheduled_timer)

        return x

    def _tk_process_queue(self):
        """Used internally to actually process the tk task queue."""
        while True:
            try:
                x = self.__tk_queue.get(block=False)
            except queue.Empty:
                break  # empty queue - we're done!
            else:
                # noinspection PyBroadException
                try:
                    if not x.cancelled:
                        x.job()
                except Exception as ex:
                    self.tkloop_exception_happened(*sys.exc_info(), x.job.func)
