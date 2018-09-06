#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example retrieve pushes with iterator.
"""
import asyncio
import datetime
import os
import pprint
import sys
import threading
import tkinter as tk
import traceback
from functools import partial
import queue
from typing import List, Callable

from asyncpushbullet.async_pushbullet import PushbulletAsyncIterator
from tkinter_tools import BindableTextArea

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


class RetrievingAllPushesApp():
    def __init__(self, root):
        self.window = root  # type: tk.Tk
        root.title("Retrieve All Pushes")

        # Data
        self.pushbullet = None  # type: AsyncPushbullet
        self.push_count_var = tk.StringVar()  # Current count as pushes keep coming in
        self.details_var = tk.StringVar()  # Details about a push
        self.pushes = []  # type: List[dict]
        self.push_iterator = None  # type: PushbulletAsyncIterator[dict]
        self.ioloop = None  # type: asyncio.BaseEventLoop

        self._tk_queue = queue.Queue()  # For managing inter-thread communication
        self._tk_after_id = None  # For managing tk.x.after(...)

        # View / Control
        self.push_listbox = None  # type: tk.Listbox
        self.retrieve_btn = None  # type: tk.Button
        self.pause_btn = None  # type: tk.Button
        self.create_widgets()

        # Connections
        self.create_io_loop()

    def create_io_loop(self):
        """Creates a new thread to manage an asyncio event loop specifically for IO to/from Pushbullet."""
        assert self.ioloop is None  # This should only ever be run once

        def _run(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self.ioloop = asyncio.new_event_loop()
        threading.Thread(target=partial(_run, self.ioloop), name="Thread-asyncio", daemon=True).start()

    def tk_schedule(self, cmd: Callable, *kargs):
        """Schedule a command to be called on the main GUI event thread."""

        def _process_tk_queue():
            while not self._tk_queue.empty():
                msg = self._tk_queue.get()  # type: Callable
                msg()

        self._tk_queue.put(partial(cmd, *kargs))
        if self._tk_after_id:
            self.window.after_cancel(self._tk_after_id)
        self._tk_after_id = self.window.after(5, _process_tk_queue)

    def create_widgets(self):

        # Buttons
        self.retrieve_btn = tk.Button(self.window, text="Retrieve Pushes!", command=self.retrieve_button_clicked)
        self.retrieve_btn.grid(row=0, column=0, sticky=tk.W, padx=10)
        self.pause_btn = tk.Button(self.window, text="Pause", command=self.pause_button_clicked)
        self.pause_btn.grid(row=0, column=1, sticky=tk.W, padx=10)
        self.pause_btn.configure(state=tk.DISABLED)

        # Count of pushes
        lbl_data = tk.Label(self.window, text="Number of Pushes:")
        lbl_data.grid(row=1, column=0, sticky=tk.W, padx=10)
        lbl_num_pushes = tk.Label(self.window, textvar=self.push_count_var)
        lbl_num_pushes.grid(row=1, column=1, padx=10, sticky=tk.W)

        # List of pushes
        scrollbar = tk.Scrollbar(self.window, orient=tk.VERTICAL)
        scrollbar.grid(row=2, column=3, sticky="NS")
        self.push_listbox = tk.Listbox(self.window, yscrollcommand=scrollbar.set, width=60, height=20)
        scrollbar.config(command=self.push_listbox.yview)
        self.push_listbox.grid(row=2, column=0, columnspan=2, sticky="NSEW")
        self.push_listbox.bind("<Double-Button-1>", self.push_list_double_clicked)
        tk.Grid.columnconfigure(self.window, 0, weight=1)
        tk.Grid.columnconfigure(self.window, 1, weight=1)
        tk.Grid.rowconfigure(self.window, 2, weight=1)

        # Push details
        txt_details = BindableTextArea(self.window, textvariable=self.details_var, width=60, height=10)
        txt_details.grid(row=2, column=4, sticky="NSEW")
        tk.Grid.columnconfigure(self.window, 4, weight=1)

    def retrieve_button_clicked(self):
        if self.push_iterator is None:
            self.retrieve_btn.configure(state=tk.DISABLED)

            def _recv_push(x):  # Run on main event thread
                pos = len(self.pushes) + 1
                title = x.get("title")
                body = x.get("body")
                creation = float(x.get("created", 0.0))
                creation = datetime.datetime.fromtimestamp(creation).strftime('%c')
                push_str = "{}. {}: {}, {}".format(pos, creation, title, body)

                self.pushes.append(x)
                self.push_count_var.set("{:,}".format(len(self.pushes)))
                self.push_listbox.insert(tk.END, push_str)

            async def _listen():
                asyncio.get_event_loop().set_debug(True)
                try:
                    async with AsyncPushbullet(API_KEY, proxy=PROXY) as self.pushbullet:
                        self.pause_btn.configure(state=tk.NORMAL)
                        self.pushes.clear()

                        # Two ways to handle GUI manipulation.  Since these are
                        # just two-off commands, not in a loop, it doesn't matter
                        # very much which we use.
                        # Technique 1
                        # self.push_count_var.set(len(self.pushes))
                        # self.push_listbox.delete(0, tk.END)
                        # await asyncio.sleep(0)
                        # Technique 2
                        self.tk_schedule(self.push_count_var.set, len(self.pushes))
                        self.tk_schedule(self.push_listbox.delete, 0, tk.END)

                        self.push_iterator = self.pushbullet.pushes_asynciter(limit=None,
                                                                              modified_after=0.0,
                                                                              active_only=True
                                                                              )
                        async for push in self.push_iterator:
                            # As pushes are retrieved -- it will take several calls to pushbullet
                            # to retrieve the long history of pushes -- they are processed on
                            # this async for loop.  Although the for loop obviously only processes
                            # one item at a time, they will come in bunches.  When a network request
                            # is processed, a batch of pushes maybe 1 to 20 will fire through quickly.
                            # We immediately schedule processing on the main thread, since we'll
                            # be updating the GUI.
                            self.tk_schedule(_recv_push, push)

                except Exception as ex:
                    print("Exception:", ex, file=sys.stderr, flush=True)
                    tb = sys.exc_info()[2]
                    traceback.print_tb(tb)

                    self.retrieve_btn.configure(state=tk.NORMAL)
                    self.pause_btn.configure(state=tk.DISABLED)
                else:
                    self.retrieve_btn.configure(text="Completed")
                    self.pause_btn.configure(text="Completed")
                    self.retrieve_btn.configure(state=tk.DISABLED)
                    self.pause_btn.configure(state=tk.DISABLED)
                    self.tk_schedule(self.push_count_var.set, "{:,} (Completed)".format(len(self.pushes)))

            asyncio.run_coroutine_threadsafe(_listen(), self.ioloop)
        else:
            self.push_iterator.resume()

    def pause_button_clicked(self):
        if self.push_iterator:
            # self.push_iterator.stop()
            # asyncio.run_coroutine_threadsafe(self.push_iterator.pause(), self.ioloop)
            self.push_iterator.pause()
            self.retrieve_btn.configure(state=tk.NORMAL)

    def push_list_double_clicked(self, event):
        items = self.push_listbox.curselection()
        if len(items) == 0:
            print("No item selected")
            return

        push = self.pushes[int(items[0])]
        self.details_var.set(pprint.pformat(push))


def main():
    tk1 = tk.Tk()
    _ = RetrievingAllPushesApp(tk1)
    tk1.mainloop()


if __name__ == '__main__':
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    try:
        main()
    except KeyboardInterrupt:
        print("Quitting")
        pass
