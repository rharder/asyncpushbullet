#!/usr/bin/env python3
"""
Tool for managing Pushbullet account
"""
import threading
import tkinter as tk
import asyncio

import logging

import sys
from functools import partial
from pprint import pprint
from tkinter import ttk

# from tkinter_tools import BindableTextArea
from typing import List

from asyncpushbullet import tkinter_tools, Device

# sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import PushListener
from asyncpushbullet.helpers import print_function_name

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = ""

logging.basicConfig(level=logging.DEBUG)


class GuiToolApp():
    def __init__(self, root):
        self.window = root
        root.title("Pushbullet Account Management")
        self.log = logging.getLogger(__name__)

        # Data
        self._pushbullet = None  #AsyncPushbullet(proxy=PROXY)  # type: AsyncPushbullet
        self.pushbullet_listener = None  # type: PushListener
        self.key_var = tk.StringVar()  # API key
        self.pushes_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.ioloop = None  # type: asyncio.BaseEventLoop

        # IO Loop
        self.create_io_loop()

        # View / Control
        self.btn_connect = None  # type: tk.Button
        self.btn_disconnect = None  # type: tk.Button
        self.lb_device = None  # type: tk.Listbox
        self.btn_load_devices = None  # type: tk.Button
        self.create_widgets()

        # Connections
        self.key_var.set(API_KEY)
        # tkinter_tools.bind_tk_var_to_property(self.pushbullet, "api_key", self.key_var)

    @property
    def status(self):
        return str(self.status_var.get())

    @status.setter
    def status(self, val):
        self.status_var.set(str(val))

    @property
    def pushbullet(self):
        current_key = self.key_var.get()
        if self._pushbullet is not None:
            if current_key != self._pushbullet.api_key:
                self._pushbullet.close_all()
                self._pushbullet = None
        if self._pushbullet is None:
            self._pushbullet = AsyncPushbullet(api_key=current_key,
                                                  loop=self.ioloop,
                                                  verify_ssl=False,
                                                  proxy=PROXY)

        return self._pushbullet

    @pushbullet.setter
    def pushbullet(self, val):
        if val is None and self._pushbullet is not None:
            self._pushbullet.close_all()
        self._pushbullet = val


    def create_io_loop(self):

        def _run(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self.ioloop = asyncio.new_event_loop()
        t = threading.Thread(target=partial(_run, self.ioloop))
        t.daemon = True
        t.start()
        print("main loop", id(asyncio.get_event_loop()))
        print("ioloop", id(self.ioloop))


    def create_widgets(self):
        """
        API Key: [                  ]
                 <Connect>
        Pushes:
        +----------------------------+
        |                            |
        +----------------------------+
        """
        parent = self.window

        # API Key
        lbl_key = tk.Label(parent, text="API Key:")
        lbl_key.grid(row=0, column=0, sticky=tk.W)
        txt_key = tk.Entry(parent, textvariable=self.key_var)
        txt_key.grid(row=0, column=1, sticky=tk.W + tk.E, columnspan=2)
        tk.Grid.grid_columnconfigure(parent, 1, weight=1)

        # Top level notebook
        notebook = ttk.Notebook(parent)
        notebook.grid(row=1, column=0, sticky="NSEW", columnspan=2)
        # tk.Grid.grid_columnconfigure(parent, 0, weight=1)
        tk.Grid.grid_rowconfigure(parent, 1, weight=1)

        # Status line
        status_label = tk.Label(parent, textvar=self.status_var)
        status_label.grid(row=999, column=0, sticky=tk.W, columnspan=2)

        # # Tab: API Key
        # api_key_frame = tk.Frame(notebook)
        # notebook.add(api_key_frame, text="API Key")
        # self.create_widgets_api_key(api_key_frame)

        # Tab: Pushes
        pushes_frame = tk.Frame(notebook)
        notebook.add(pushes_frame, text="Pushes")
        self.create_widgets_pushes(pushes_frame)

        # Tab: Devices
        devices_frame = tk.Frame(notebook)
        notebook.add(devices_frame, text="Devices")
        self.create_widgets_devices(devices_frame)



    def create_widgets_pushes(self, parent: tk.Frame):

        self.btn_connect = tk.Button(parent, text="Connect", command=self.connect_button_clicked)
        self.btn_connect.grid(row=0, column=0, sticky=tk.W)

        self.btn_disconnect = tk.Button(parent, text="Disconnect", command=self.disconnect_button_clicked)
        self.btn_disconnect.grid(row=0, column=1, sticky=tk.W)
        self.btn_disconnect.configure(state=tk.DISABLED)
        # tk.Grid.grid_columnconfigure(parent, 2, weight=1)

        # lbl_data = tk.Label(parent, text="Incoming Pushes...")
        # lbl_data.grid(row=1, column=0, sticky=tk.W, columnspan=2)
        txt_data = tkinter_tools.BindableTextArea(parent, textvariable=self.pushes_var, width=80, height=10)
        txt_data.grid(row=1, column=0, sticky="NSEW", columnspan=2)
        tk.Grid.grid_columnconfigure(parent, 0, weight=1)
        tk.Grid.grid_columnconfigure(parent, 1, weight=1)
        tk.Grid.grid_rowconfigure(parent, 1, weight=1)

    def create_widgets_devices(self, parent: tk.Frame):

        scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL)
        self.lb_device = tk.Listbox(parent, yscrollcommand=scrollbar.set)
        # listbox = Listbox(frame, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.lb_device.yview)
        self.lb_device.grid(row=0, column=0, sticky="NSEW")
        # self.lb_device.insert(tk.END, "hello")
        # self.lb_device.insert(tk.END, "world")

        self.btn_load_devices = tk.Button(parent, text="Load Devices", command=self.load_devices_clicked)
        self.btn_load_devices.grid(row=1, column=0, sticky="EW")

    # ########   B U T T O N S   ########

    def connect_button_clicked(self):
        self.status = "Connecting to Pushbullet..."
        self.btn_connect.configure(state=tk.DISABLED)
        self.btn_disconnect.configure(state=tk.DISABLED)

        if self.pushbullet is not None:
            self.pushbullet.close_all()
            self.pushbullet = None
        if self.pushbullet_listener is not None:
            self.pushbullet_listener.close()

        async def _connect():
            # print_function_name(self)
            # asyncio.set_event_loop(loop)
            api_key = self.key_var.get()
            # self.pushbullet = AsyncPushbullet(api_key=api_key,
            #                                   loop=asyncio.get_event_loop(),
            #                                   verify_ssl=False,
            #                                   proxy=PROXY)
            try:
                await self.pushbullet.async_verify_key()
            except Exception as e:
                self.log.info("Invalid API Key: {}".format(api_key))
                # raise e
                self.status = "Invalid API key: {}".format(api_key)
                self.pushbullet = None
                self.btn_connect.configure(state=tk.NORMAL)
                self.btn_disconnect.configure(state=tk.DISABLED)
                return
            #
            # devs = await self.pushbullet.async_get_devices()
            # print("DEVICES")
            # pprint(devs)
            #
            # pushes = await self.pushbullet.async_get_pushes(limit=1)
            # # pushes = self.pushbullet.get_pushes(limit=1)  # stuck?
            # print("PUSHES")
            # pprint(pushes)

            self.pushbullet_listener = PushListener(self.pushbullet,
                                                    on_connect=self.pushlistener_connected,
                                                    on_message=self.push_received,
                                                    on_close=self.pushlistener_closed)
            # loop.run_forever()

        asyncio.run_coroutine_threadsafe(_connect(), self.ioloop)

        # ioloop = asyncio.new_event_loop()
        # t = threading.Thread(target=partial(_run, ioloop))
        # t.daemon = True
        # t.start()
        # print("main loop", id(asyncio.get_event_loop()))
        # print("ioloop", id(ioloop))


    def disconnect_button_clicked(self):
        self.status = "Disconnecting from Pushbullet..."
        self.btn_connect.configure(state=tk.DISABLED)
        self.btn_disconnect.configure(state=tk.DISABLED)
        self.pushbullet_listener.close()

    def load_devices_clicked(self):
        self.btn_load_devices.configure(state=tk.DISABLED)
        self.status = "Loading devices..."
        self.lb_device.delete(0, tk.END)
        self.lb_device.insert(tk.END, "Loading...")

        async def _load():
            devices = []  # type: List[Device]
            try:
                await self.verify_key()
                devices = await self.pushbullet.async_get_devices()
                self.lb_device.delete(0, tk.END)
                for dev in devices:
                    self.lb_device.insert(tk.END, str(dev.nickname))
                self.status = "Loaded {} devices".format(len(devices))

            except Exception as ex:
                # print(ex)
                # ex.with_traceback()
                self.lb_device.delete(0, tk.END)
            finally:
                self.btn_load_devices.configure(state=tk.NORMAL)
                # self.status = "Loaded {} devices".format(len(devices))


        asyncio.run_coroutine_threadsafe(_load(), self.ioloop)


    # ########   C A L L B A C K S  ########

    async def pushlistener_connected(self, listener: PushListener):
        self.status = "Connected to Pushbullet"
        self.btn_disconnect.configure(state=tk.NORMAL)

    async def pushlistener_closed(self, listener: PushListener):
        self.status = "Disconnected from Pushbullet"
        self.btn_connect.configure(state=tk.NORMAL)

    async def push_received(self, p: dict, listener: PushListener):
        print("Push received:", p)
        prev = self.pushes_var.get()
        prev += "{}\n\n".format(p)
        self.pushes_var.set(prev)

    async def verify_key(self):
        self.status = "Verifying API key..."
        valid = False
        api_key = self.key_var.get()
        try:
            await self.pushbullet.async_verify_key()
            valid = True
        except Exception as e:
            pass
            # self.log.info("Invalid API Key: {}".format(api_key))
            # raise e
            # self.status = "Invalid API key: {}".format(api_key)
            # self.pushbullet = None
            # self.btn_connect.configure(state=tk.NORMAL)
            # self.btn_disconnect.configure(state=tk.DISABLED)
            # return
        finally:
            if valid:
                self.status = "Valid API key: {}".format(api_key)
            else:
                self.status = "Invalid API key: {}".format(api_key)
            return valid


def main():
    tk1 = tk.Tk()
    program1 = GuiToolApp(tk1)

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
