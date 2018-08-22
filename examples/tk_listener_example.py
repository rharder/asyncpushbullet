#!/usr/bin/env python3
"""
Example tkinter app that shows pushes as they arrive.
"""
import os
import threading
import tkinter as tk
import asyncio

import logging

import sys
from functools import partial

# from tkinter_tools import BindableTextArea
from tkinter_tools import BindableTextArea

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import PushListener2

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY

logging.basicConfig(level=logging.DEBUG)


class PushApp():
    def __init__(self, root):
        self.window = root
        root.title("Async Pushbullet Demo")
        self.log = logging.getLogger(__name__)

        # Data
        self.pushbullet = None  # type: AsyncPushbullet
        self.pushbullet_listener = None  # type: PushListener2
        self.key_var = tk.StringVar()  # API key
        self.pushes_var = tk.StringVar()
        self.ioloop = None  # type: asyncio.BaseEventLoop
        self.proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")

        # View / Control
        self.create_widgets()

        # Connections
        self.create_io_loop()
        self.key_var.set(API_KEY)


    def create_widgets(self):
        """
        API Key: [                  ]
                 <Connect>
        Pushes:
        +----------------------------+
        |                            |
        +----------------------------+
        """
        # API Key
        lbl_key = tk.Label(self.window, text="API Key:")
        lbl_key.grid(row=0, column=0, sticky=tk.W)
        txt_key = tk.Entry(self.window, textvariable=self.key_var)
        txt_key.grid(row=0, column=1, sticky=tk.W + tk.E)
        tk.Grid.grid_columnconfigure(self.window, 1, weight=1)
        txt_key.bind('<Return>', lambda x: self.connect_button_clicked())

        btn_connect = tk.Button(self.window, text="Connect", command=self.connect_button_clicked)
        btn_connect.grid(row=1, column=1, sticky=tk.W)

        btn_disconnect = tk.Button(self.window, text="Disconnect", command=self.disconnect_button_clicked)
        btn_disconnect.grid(row=2, column=1, sticky=tk.W)

        lbl_data = tk.Label(self.window, text="Incoming Pushes...")
        lbl_data.grid(row=4, column=0, sticky=tk.W)
        txt_data = BindableTextArea(self.window, textvariable=self.pushes_var, width=80, height=10)
        txt_data.grid(row=5, column=0, columnspan=2)

    def connect_button_clicked(self):
        self.close()

        async def _listen():
            try:
                self.pushbullet = AsyncPushbullet(self.key_var.get(),
                                                  verify_ssl=False,
                                                  proxy=self.proxy)

                async with PushListener2(self.pushbullet) as pl2:
                    self.pushbullet_listener = pl2
                    await self.connected(pl2)

                    async for push in pl2:
                        await self.push_received(push, pl2)

            except Exception as ex:
                print("Exception:", ex)
            finally:
                await self.disconnected(self.pushbullet_listener)

        asyncio.run_coroutine_threadsafe(_listen(), self.ioloop)


    def create_io_loop(self):
        """Creates a new thread to manage an asyncio event loop specifically for IO to/from Pushbullet."""
        assert self.ioloop is None  # This should only ever be run once

        def _run(loop):
            loop.run_forever()

        self.ioloop = asyncio.new_event_loop()
        self.ioloop.set_exception_handler(self._ioloop_exc_handler)
        t = threading.Thread(target=partial(_run, self.ioloop))
        t.daemon = True
        t.start()

    def _ioloop_exc_handler(self, loop: asyncio.BaseEventLoop, context: dict):
        if "exception" in context:
            self.status = context["exception"]
        self.status = str(context)
        # Handle this more robustly in real-world code

    def close(self):

        if self.pushbullet is not None:
            self.pushbullet.close_all_threadsafe()
            self.pushbullet = None
        if self.pushbullet_listener is not None:
            assert self.ioloop is not None
            pl = self.pushbullet_listener
            asyncio.run_coroutine_threadsafe(pl.close(), self.ioloop)
            self.pushbullet_listener = None

    def disconnect_button_clicked(self):
        self.close()

    async def connected(self, listener: PushListener2):
        print("Connected to websocket")

    async def disconnected(self, listener: PushListener2):
        print("Disconnected from websocket")

    async def push_received(self, p: dict, listener: PushListener2):
        print("Push received:", p)
        prev = self.pushes_var.get()
        prev += "{}\n\n".format(p)
        self.pushes_var.set(prev)


def main():
    tk1 = tk.Tk()
    program1 = PushApp(tk1)

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
