#!/usr/bin/env python3
"""
Tool for managing Pushbullet account
"""
import asyncio
import io
import logging
import pprint
import sys
import threading
import tkinter as tk
from functools import partial
from tkinter import ttk
from typing import Tuple

try:
    from PIL import Image
    from PIL.ImageTk import PhotoImage
except ImportError as ie:
    print("To include image support: pip install pillow")

import tkinter_tools

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import Device
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet.async_listeners import PushListener
from asyncpushbullet.helpers import print_function_name

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = ""


# logging.basicConfig(level=logging.DEBUG)


class GuiToolApp():
    def __init__(self, root):
        self.window = root
        root.title("Pushbullet Account Management")
        self.log = logging.getLogger(__name__)

        # Data
        self._pushbullet = None  # type: AsyncPushbullet
        self.pushbullet_listener = None  # type: PushListener

        # General Data
        self.key_var = tk.StringVar()  # API key
        self.pushes_var = tk.StringVar()  # Used in text box to display pushes received
        self.status_var = tk.StringVar()  # Bound to bottom of window status bar
        self.ioloop = None  # type: asyncio.BaseEventLoop

        # Related to Devices
        self.device_detail_var = tk.StringVar()  # Used in text box to display device details
        self.devices_in_listbox = None  # type: Tuple[Device]  # Cached devices that were retrieved
        self.device_tab_index = None  # type: int  # The index for the Devices tab

        # IO Loop
        self.create_io_loop()

        # View / Control
        self.btn_connect = None  # type: tk.Button
        self.btn_disconnect = None  # type: tk.Button
        self.lb_device = None  # type: tk.Listbox
        self.btn_load_devices = None  # type: tk.Button
        self.lbl_photo = None  # type: tk.Label
        self.lbl_status = None  # type: tk.Label
        self.create_widgets()

        # Connections / Bindings
        self.key_var.set(API_KEY)

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
                                               # verify_ssl=False,
                                               proxy=PROXY)

        return self._pushbullet

    @pushbullet.setter
    def pushbullet(self, val):
        if val is None and self._pushbullet is not None:
            self._pushbullet.close_all()
        self._pushbullet = val

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
        print("_exc_handler", loop, context)
        pprint.pprint(context)
        if "exception" in context:
            self.status = context["exception"]
            self.pushbullet = None
            self.btn_connect.configure(state=tk.NORMAL)
            self.btn_disconnect.configure(state=tk.DISABLED)
        self.status = str(context)

    def create_widgets(self):

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

        notebook.bind("<<NotebookTabChanged>>", self.notebook_tab_changed)

        # Status line
        status_line = tk.Frame(parent)
        status_line.grid(row=999, column=0, sticky=tk.W, columnspan=2)
        self.lbl_photo = tk.Label(status_line)  # , text="", width=16, height=16)
        self.lbl_photo.grid(row=0, column=0, sticky=tk.W)
        self.lbl_status = tk.Label(status_line, textvar=self.status_var)
        self.lbl_status.grid(row=0, column=1, sticky=tk.W)

        # Tab: Pushes
        pushes_frame = tk.Frame(notebook)
        notebook.add(pushes_frame, text="Pushes")
        self.create_widgets_pushes(pushes_frame)

        # Tab: Devices
        devices_frame = tk.Frame(notebook)
        notebook.add(devices_frame, text="Devices")
        self.device_tab_index = notebook.index(tk.END) - 1  # save tab pos for later
        self.create_widgets_devices(devices_frame)

    def create_widgets_pushes(self, parent: tk.Frame):

        self.btn_connect = tk.Button(parent, text="Connect", command=self.connect_button_clicked)
        self.btn_connect.grid(row=0, column=0, sticky=tk.W)

        self.btn_disconnect = tk.Button(parent, text="Disconnect", command=self.disconnect_button_clicked)
        self.btn_disconnect.grid(row=0, column=1, sticky=tk.W)
        self.btn_disconnect.configure(state=tk.DISABLED)

        txt_data = tkinter_tools.BindableTextArea(parent, textvariable=self.pushes_var, width=60, height=20)
        txt_data.grid(row=1, column=0, sticky="NSEW", columnspan=2)
        tk.Grid.grid_columnconfigure(parent, 0, weight=1)
        tk.Grid.grid_columnconfigure(parent, 1, weight=1)
        tk.Grid.grid_rowconfigure(parent, 1, weight=1)

    def create_widgets_devices(self, parent: tk.Frame):

        scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL)
        self.lb_device = tk.Listbox(parent, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.lb_device.yview)
        self.lb_device.grid(row=0, column=0, sticky="NSEW")
        self.lb_device.bind("<Double-Button-1>", self.device_list_double_clicked)

        self.btn_load_devices = tk.Button(parent, text="Load Devices", command=self.load_devices_clicked)
        self.btn_load_devices.grid(row=1, column=0, sticky="EW")

        txt_device_details = tkinter_tools.BindableTextArea(parent, textvariable=self.device_detail_var, width=80,
                                                            height=10)
        txt_device_details.grid(row=0, column=1, sticky="NSEW")
        tk.Grid.grid_columnconfigure(parent, 1, weight=1)
        tk.Grid.grid_rowconfigure(parent, 0, weight=1)

    # ########   G U I   E V E N T S   ########

    def notebook_tab_changed(self, event):
        nb = event.widget  # type: ttk.Notebook
        index = nb.index("current")
        if index == self.device_tab_index:
            # print("Devices!")
            # If there are no devices loaded, go ahead and try
            if self.devices_in_listbox is None:
                self.load_devices_clicked()

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

            try:
                await self.verify_key()
            except:
                self.btn_connect.configure(state=tk.NORMAL)
                self.btn_disconnect.configure(state=tk.DISABLED)
            else:
                self.pushbullet_listener = PushListener(self.pushbullet,
                                                        on_connect=self.pushlistener_connected,
                                                        on_message=self.push_received,
                                                        on_close=self.pushlistener_closed)
                self.btn_connect.configure(state=tk.DISABLED)
                self.btn_disconnect.configure(state=tk.NORMAL)

            # if await self.verify_key():
            #     self.pushbullet_listener = PushListener(self.pushbullet,
            #                                             on_connect=self.pushlistener_connected,
            #                                             on_message=self.push_received,
            #                                             on_close=self.pushlistener_closed)
            #     self.btn_connect.configure(state=tk.DISABLED)
            #     self.btn_disconnect.configure(state=tk.NORMAL)
            # else:
            #     self.btn_connect.configure(state=tk.NORMAL)
            #     self.btn_disconnect.configure(state=tk.DISABLED)

        asyncio.run_coroutine_threadsafe(_connect(), self.ioloop)

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
        self.devices_in_listbox = None

        async def _load():
            try:
                await self.verify_key()
                self.devices_in_listbox = tuple(await self.pushbullet.async_get_devices())
                self.lb_device.delete(0, tk.END)
                for dev in self.devices_in_listbox:
                    self.lb_device.insert(tk.END, str(dev.nickname))
                self.status = "Loaded {} devices".format(len(self.devices_in_listbox))

            except Exception as ex:
                self.lb_device.delete(0, tk.END)
                raise ex
            finally:
                self.btn_load_devices.configure(state=tk.NORMAL)

        asyncio.run_coroutine_threadsafe(_load(), self.ioloop)

    def device_list_double_clicked(self, event):
        items = self.lb_device.curselection()
        if len(items) == 0:
            print("No item selected")
            return

        if self.devices_in_listbox is None:
            print("No devices have been loaded")

        device = self.devices_in_listbox[int(items[0])]
        self.device_detail_var.set(repr(device))

    # ########   C A L L B A C K S  ########

    async def pushlistener_connected(self, listener: PushListener):
        self.status = "Connected to Pushbullet"
        try:
            me = self.pushbullet.user_info
            self.status = "Connected to Pushbullet: {}".format(me.get("name"))

        except Exception as ex:
            # print("To include image support: pip install pillow")
            pass
        finally:
            self.btn_connect.configure(state=tk.DISABLED)
            self.btn_disconnect.configure(state=tk.NORMAL)

    async def pushlistener_closed(self, listener: PushListener):
        print_function_name()
        self.status = "Disconnected from Pushbullet"
        self.btn_connect.configure(state=tk.NORMAL)
        self.btn_disconnect.configure(state=tk.DISABLED)

    async def push_received(self, p: dict, listener: PushListener):
        # print("Push received:", p)
        prev = self.pushes_var.get()
        prev += "{}\n\n".format(pprint.pformat(p))
        self.pushes_var.set(prev)

    # ########  O T H E R  ########

    async def verify_key(self):
        self.status = "Verifying API key..."
        api_key = self.key_var.get()

        try:
            await self.pushbullet.async_verify_key()
            self.status = "Valid API key: {}".format(api_key)

            if getattr(self.lbl_photo, "image_ref", None) is None:
                async def _load_pic():
                    try:
                        me = self.pushbullet.user_info
                        if "image_url" in me:
                            image_url = me.get("image_url")
                            try:
                                msg = await self.pushbullet._async_get_data(image_url)
                            except Exception as ex_get:
                                self.log.info("Could not retrieve user photo from url {}".format(image_url))
                            else:
                                photo_bytes = io.BytesIO(msg.get("raw"))
                                img = Image.open(photo_bytes)
                                label_size = self.lbl_photo.winfo_height()
                                img = img.resize((label_size, label_size), Image.ANTIALIAS)
                                photo = PhotoImage(img)
                                self.lbl_photo.configure(image=photo)
                                self.lbl_photo.image_ref = photo  # Save for garbage collection protection
                                self.log.info("Loaded user image from url {}".format(image_url))

                    except Exception as ex:
                        print(ex)
                        print("To include image support: pip install pillow")
                        ex.with_traceback()
                        raise ex

                asyncio.get_event_loop().create_task(_load_pic())

        except Exception as e:
            self.status = "Invalid API key: {}".format(api_key)
            self.lbl_photo.configure(image="")
            self.lbl_photo.image_ref = None
            raise e


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
