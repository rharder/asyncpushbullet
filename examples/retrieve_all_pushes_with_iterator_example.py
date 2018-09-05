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
from functools import partial
from typing import List

from tkinter_tools import BindableTextArea

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


class RetrievingAllPushesApp():
    def __init__(self, root):
        self.window = root
        root.title("Retrieve All Pushes")

        # Data
        self.pushbullet = None  # type: AsyncPushbullet
        self.push_count_var = tk.IntVar()  # Current count as pushes keep coming in
        self.details_var = tk.StringVar()  # Details about a push
        self.pushes = []  # type: List[dict]
        self.ioloop = None  # type: asyncio.BaseEventLoop

        # View / Control
        self.push_listbox = None  # type: tk.Listbox
        self.retrieve_btn = None  # type: tk.Button
        self.abort_btn = None  # type: tk.Button
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

    def create_widgets(self):

        self.retrieve_btn = tk.Button(self.window, text="Retrieve Pushes!", command=self.connect_button_clicked)
        self.retrieve_btn.grid(row=0, column=0, sticky=tk.W, padx=10)
        self.abort_btn = tk.Button(self.window, text="Abort!", command=self.abort_button_clicked)
        self.abort_btn.grid(row=0, column=1, sticky=tk.W, padx=10)
        self.abort_btn.configure(state=tk.DISABLED)

        lbl_data = tk.Label(self.window, text="Number of Pushes:")
        lbl_data.grid(row=1, column=0, sticky=tk.W, padx=10)
        lbl_num_pushes = tk.Label(self.window, textvar=self.push_count_var)
        lbl_num_pushes.grid(row=1, column=1, padx=10, sticky=tk.W)

        scrollbar = tk.Scrollbar(self.window, orient=tk.VERTICAL)
        scrollbar.grid(row=2, column=3, sticky="NS")
        self.push_listbox = tk.Listbox(self.window, yscrollcommand=scrollbar.set, width=60, height=20)
        scrollbar.config(command=self.push_listbox.yview)
        self.push_listbox.grid(row=2, column=0, columnspan=2, sticky="NSEW")
        self.push_listbox.bind("<Double-Button-1>", self.push_list_double_clicked)
        tk.Grid.columnconfigure(self.window, 0, weight=1)
        tk.Grid.columnconfigure(self.window, 1, weight=1)
        tk.Grid.rowconfigure(self.window, 2, weight=1)

        txt_details = BindableTextArea(self.window, textvariable=self.details_var, width=60, height=10)
        txt_details.grid(row=2, column=4, sticky="NSEW")
        tk.Grid.columnconfigure(self.window, 4, weight=1)

    def connect_button_clicked(self):
        self.retrieve_btn.configure(state=tk.DISABLED)
        async def _listen():
            try:
                async with AsyncPushbullet(API_KEY, proxy=PROXY) as self.pushbullet:
                    self.abort_btn.configure(state=tk.NORMAL)

                    self.pushes.clear()
                    self.push_count_var.set(len(self.pushes))
                    self.push_listbox.delete(0, tk.END)

                    async for push in self.pushbullet.async_pushes_iter(limit=0, page_size=None):
                        # As pushes are retrieved -- it will take several calls to pushbullet
                        # to retrieve the long history of pushes -- they are processed on
                        # this async for loop.  Although the for loop obviously only processes
                        # one item at a time, they will come in bunches.  When a network request
                        # is processed, a batch of pushes maybe 1 to 20 will fire through quickly.
                        title = push.get("title")
                        body = push.get("body")
                        creation = float(push.get("created",0.0))
                        creation = datetime.datetime.fromtimestamp(creation).strftime('%c')

                        self.pushes.append(push)
                        self.push_count_var.set(len(self.pushes))
                        self.push_listbox.insert(tk.END, "{}: {}, {}".format(creation, title, body))

            except Exception as ex:
                print("Exception:", ex)
            finally:
                self.retrieve_btn.configure(state=tk.NORMAL)
                self.abort_btn.configure(state=tk.DISABLED)

        asyncio.run_coroutine_threadsafe(_listen(), self.ioloop)

    def abort_button_clicked(self):
        if self.pushbullet:
            self.pushbullet.close_all_threadsafe()

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
