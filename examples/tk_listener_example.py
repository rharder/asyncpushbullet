#!/usr/bin/env python3
"""
Example tkinter app that shows pushes as they arrive.
"""
import threading
import tkinter as tk
import asyncio

import logging

import sys
from functools import partial

from tkinter_tools import BindableTextArea

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import PushListener

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
        self.pushbullet_listener = None  # type: PushListener
        self.key_var = tk.StringVar()  # API key
        self.pushes_var = tk.StringVar()

        # View / Control
        self.create_widgets()

        # Connections
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

        lbl_data = tk.Label(self.window, text="Incoming Pushes...")
        lbl_data.grid(row=4, column=0, sticky=tk.W)
        txt_data = BindableTextArea(self.window, textvariable=self.pushes_var, width=80, height=10)
        txt_data.grid(row=5, column=0, columnspan=2)

    def connect_button_clicked(self):
        if self.pushbullet is not None:
            self.pushbullet.close()
            self.pushbullet = None
        if self.pushbullet_listener is not None:
            self.pushbullet_listener.close()

        def _run(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()
        ioloop = asyncio.new_event_loop()
        t = threading.Thread(target=partial(_run, ioloop))
        t.daemon = True
        t.start()
        print("main loop", id(asyncio.get_event_loop()))
        print("ioloop", id(ioloop))

        self.pushbullet = AsyncPushbullet(self.key_var.get(), loop=ioloop, verify_ssl=False)
        self.pushbullet_listener = PushListener(self.pushbullet,
                                                on_connect=self.connected,
                                                on_message=self.push_received)


    async def connected(self, listener: PushListener):
        print("Connected to websocket")
        # await listener.account.async_push_note("Connected to websocket", "Connected to websocket")

    async def push_received(self, p: dict, listener: PushListener):
        print("Push received:", p)
        prev = self.pushes_var.get()
        prev += "{}\n\n".format(p)
        self.pushes_var.set(prev)


def main():
    tk1 = tk.Tk()
    program1 = PushApp(tk1)

    # tk2 = tk.Toplevel()
    # program2 = PushApp(tk2)

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
