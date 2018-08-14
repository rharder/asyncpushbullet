#!/usr/bin/env python3
"""
UNDER CONSTRUCTION
Example tkinter app that uploads files and shows incoming pushes.
"""
import threading
import tkinter as tk
import asyncio

import logging

import sys
from functools import partial
from tkinter import filedialog

from tkinter_tools import BindableTextArea

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import PushListener

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = ""


# logging.basicConfig(level=logging.DEBUG)


class PushApp():
    def __init__(self, root):
        self.window = root
        root.title("Async Pushbullet Upload Demo")
        self.log = logging.getLogger(__name__)

        # Data
        self.ioloop = None  # type: asyncio.AbstractEventLoop
        self.pushbullet = None  # type: AsyncPushbullet
        self.pushbullet_listener = None  # type: PushListener
        self.key_var = tk.StringVar()  # API key
        self.pushes_var = tk.StringVar()
        self.filename_var = tk.StringVar()
        self.btn_upload = None  # type: tk.Button

        # View / Control
        self.create_widgets()

        # Connections
        self.key_var.set(API_KEY)
        self.filename_var.set(__file__)

    def create_widgets(self):
        """
        API Key: [                  ]
                 <Connect>
        Filename: [                 ]
            <Browse>  <Upload>
        Pushes:
        +----------------------------+
        |                            |
        +----------------------------+
        """
        row = 0
        # API Key
        lbl_key = tk.Label(self.window, text="API Key:")
        lbl_key.grid(row=row, column=0, sticky=tk.W)
        txt_key = tk.Entry(self.window, textvariable=self.key_var)
        txt_key.grid(row=row, column=1, sticky=tk.W + tk.E)
        tk.Grid.grid_columnconfigure(self.window, 1, weight=1)
        txt_key.bind('<Return>', lambda x: self.connect_button_clicked())
        row += 1
        btn_connect = tk.Button(self.window, text="Connect", command=self.connect_button_clicked)
        btn_connect.grid(row=row, column=1, sticky=tk.W)
        row += 1

        # File: [    ]
        lbl_file = tk.Label(self.window, text="File:")
        lbl_file.grid(row=row, column=0, sticky=tk.W)
        txt_file = tk.Entry(self.window, textvariable=self.filename_var)
        txt_file.grid(row=row, column=1, sticky=tk.W + tk.E)
        row += 1

        # <Browse>  <Upload>
        button_frame = tk.Frame(self.window)
        button_frame.grid(row=row, column=0, columnspan=2, sticky=tk.W + tk.E)
        row += 1
        btn_browse = tk.Button(button_frame, text="Browse...", command=self.browse_button_clicked)
        btn_browse.grid(row=0, column=0, sticky=tk.E)
        self.btn_upload = tk.Button(button_frame, text="Upload and Push", command=self.upload_button_clicked,
                                    state=tk.DISABLED)
        self.btn_upload.grid(row=0, column=1, sticky=tk.W)

        # Incoming pushes
        # +------------+
        # |            |
        # +------------+
        lbl_data = tk.Label(self.window, text="Incoming Pushes...")
        lbl_data.grid(row=row, column=0, sticky=tk.W)
        row += 1
        txt_data = BindableTextArea(self.window, textvariable=self.pushes_var, width=80, height=10)
        txt_data.grid(row=row, column=0, columnspan=2)

    def connect_button_clicked(self):
        self.pushes_var.set("Connecting...")

        if self.pushbullet is not None:
            self.pushbullet.close()
            self.pushbullet = None
        if self.pushbullet_listener is not None:
            self.pushbullet_listener.close()
            self.pushbullet_listener = None

        def _run(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self.ioloop = asyncio.new_event_loop()
        t = threading.Thread(target=partial(_run, self.ioloop))
        t.daemon = True
        t.start()

        self.pushbullet = AsyncPushbullet(self.key_var.get(), loop=self.ioloop, verify_ssl=False,
                                          proxy=PROXY)
        self.pushbullet_listener = PushListener(self.pushbullet,
                                                on_connect=self.connected,
                                                on_message=self.push_received)

    def browse_button_clicked(self):
        print("browse_button_clicked")
        resp = filedialog.askopenfilename(parent=self.window, title="Open a File to Push")
        if resp != "":
            self.filename_var.set(resp)

    def upload_button_clicked(self):
        self.pushes_var.set(self.pushes_var.get() + "Uploading...")
        self.btn_upload["state"] = tk.DISABLED
        filename = self.filename_var.get()
        asyncio.run_coroutine_threadsafe(self.upload_file(filename), loop=self.ioloop)

    async def upload_file(self, filename: str):
        info = await self.pushbullet.async_upload_file(filename)

        # Push as a file:
        await self.pushbullet.async_push_file(info["file_name"], info["file_url"], info["file_type"],
                                              title="File Arrived!", body="Please enjoy your file")

        # Push as a link:
        await self.pushbullet.async_push_link("Link to File Arrived!", info["file_url"], body="Please enjoy your file")
        self.btn_upload["state"] = tk.NORMAL
        self.pushes_var.set(self.pushes_var.get() + "Uploaded\n")

    async def connected(self, listener: PushListener):
        self.btn_upload["state"] = tk.NORMAL
        self.pushes_var.set(self.pushes_var.get() + "Connected\n")

    async def push_received(self, p: dict, listener: PushListener):
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
        if PROXY == "":
            with open("../proxy.txt") as f:
                PROXY = f.read().strip()
    except Exception as e:
        pass  # No proxy file, that's OK

    try:
        main()
    except KeyboardInterrupt:
        print("Quitting")
        pass
