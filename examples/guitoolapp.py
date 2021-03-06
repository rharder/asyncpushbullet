#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool for managing Pushbullet account
"""
import asyncio
import io
import logging
import os
import pprint
import sys
import tkinter as tk
from functools import partial
from tkinter import ttk
from typing import Tuple

from tk_asyncio_base import TkAsyncioBaseApp

try:
    from PIL import Image
    from PIL.ImageTk import PhotoImage
except ImportError as ie:
    print("To include image support: pip install pillow")

import tkinter_tools

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import Device, oauth2
from asyncpushbullet import AsyncPushbullet
from asyncpushbullet import LiveStreamListener
from asyncpushbullet.prefs import Prefs

__author__ = 'Robert Harder'
__email__ = "rob@iharder.net"

PREFS = Prefs("asyncpushbullet.guitoolapp", "net.iharder.asyncpushbullet")
API_KEY = PREFS.get("api_key")


class GuiToolApp(TkAsyncioBaseApp):
    def __init__(self, root):
        super().__init__(root)
        self.window = root
        root.title("Pushbullet Account Management")
        self.log = logging.getLogger(__name__)

        # Data
        self._pushbullet = None  # type: AsyncPushbullet
        self.pushbullet_listener = None  # type: LiveStreamListener
        self.key_var = tk.StringVar()  # type: tk.StringVar  # API key
        self.pushes_var = tk.StringVar()  # type: tk.StringVar  # Used in text box to display pushes received
        self.status_var = tk.StringVar()  # type: tk.StringVar  # Bound to bottom of window status bar
        self.proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")  # type: str

        # Related to Devices
        self.device_detail_var = tk.StringVar()  # type: tk.StringVar  # Used in text box to display device details
        self.devices_in_listbox = None  # type: Tuple[Device]  # Cached devices that were retrieved
        self.device_tab_index = None  # type: int  # The index for the Devices tab

        # View / Control
        self.btn_connect = None  # type: tk.Button
        self.btn_disconnect = None  # type: tk.Button
        self.lb_device = None  # type: tk.Listbox
        self.btn_load_devices = None  # type: tk.Button
        self.lbl_photo = None  # type: tk.Label
        self.lbl_status = None  # type: tk.Label
        self.create_widgets()

        # Connections / Bindings
        tkinter_tools.bind_tk_var_to_method(partial(PREFS.set, "api_key"), self.key_var)
        self.key_var.set(API_KEY)

    @property
    def status(self):
        return str(self.status_var.get())

    @status.setter
    def status(self, val):
        self.tk(self.status_var.set, val)

    @property
    def pushbullet(self) -> AsyncPushbullet:
        current_key = self.key_var.get()
        if self._pushbullet is not None:
            if current_key != self._pushbullet.api_key:
                self._pushbullet.close_all_threadsafe()
                self._pushbullet = None
        if self._pushbullet is None:
            self._pushbullet = AsyncPushbullet(api_key=current_key,
                                               # loop=self.ioloop,
                                               verify_ssl=False,
                                               proxy=self.proxy)

        return self._pushbullet

    @pushbullet.setter
    def pushbullet(self, val: AsyncPushbullet):
        if val is None and self._pushbullet is not None:
            self._pushbullet.close_all_threadsafe()
        self._pushbullet = val

    def ioloop_exception_happened(self, extype, ex, tb, func):
        self.status = ex

    def create_widgets(self):
        parent = self.window

        # API Key
        frm_key = tk.Frame(parent)
        frm_key.grid(row=0, column=0, sticky="NSEW")
        lbl_key = tk.Label(frm_key, text="API Key:")
        lbl_key.grid(row=0, column=0, sticky=tk.W)
        txt_key = tk.Entry(frm_key, textvariable=self.key_var)
        txt_key.grid(row=0, column=1, sticky=tk.W + tk.E, columnspan=2)
        btn_oauth2 = tk.Button(frm_key, text="Authenticate online...")
        btn_oauth2.configure(command=partial(self.oauth2_clicked, btn_oauth2))
        btn_oauth2.grid(row=0, column=2, sticky=tk.W)
        tk.Grid.grid_columnconfigure(frm_key, 1, weight=1)
        tk.Grid.grid_columnconfigure(parent, 0, weight=1)

        # Top level notebook
        notebook = ttk.Notebook(parent)
        notebook.grid(row=1, column=0, sticky="NSEW", columnspan=2)
        # tk.Grid.grid_columnconfigure(parent, 0, weight=1)
        tk.Grid.grid_rowconfigure(parent, 1, weight=1)

        notebook.bind("<<NotebookTabChanged>>", self.notebook_tab_changed)

        # Status line
        status_line = tk.Frame(parent, borderwidth=2, relief=tk.GROOVE)
        status_line.grid(row=999, column=0, sticky="EW", columnspan=2)
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

        btn_clear = tk.Button(parent, text="Clear", command=partial(self.pushes_var.set, ""))
        btn_clear.grid(row=0, column=2)

        txt_data = tkinter_tools.BindableTextArea(parent, textvariable=self.pushes_var, width=60, height=20)
        txt_data.grid(row=1, column=0, sticky="NSEW", columnspan=3)
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
            # If there are no devices loaded, go ahead and try
            if self.devices_in_listbox is None:
                self.load_devices_clicked()

    def oauth2_clicked(self, btn: tk.Button):
        btn.configure(state=tk.DISABLED)
        self.status = "Authenticating online using OAuth2..."

        async def _auth():
            token = await oauth2.async_gain_oauth2_access()
            if token:
                self.tk(self.key_var.set, token)
                self.status = "Authentication using OAuth2 succeeded."
            else:
                self.status = "Authentication using OAuth2 failed."
            btn.configure(state=tk.NORMAL)

        self.io(_auth())

    def connect_button_clicked(self):
        self.status = "Connecting to Pushbullet..."
        self.btn_connect.configure(state=tk.DISABLED)
        self.btn_disconnect.configure(state=tk.DISABLED)

        if self.pushbullet is not None:
            self.pushbullet = None
        if self.pushbullet_listener is not None:
            pl = self.pushbullet_listener  # type: LiveStreamListener
            if pl is not None:
                self.io(pl.close())
            self.pushbullet_listener = None

        async def _listen():
            pl2 = None  # type: LiveStreamListener
            try:
                await self.verify_key()
                async with LiveStreamListener(self.pushbullet, types=()) as pl2:
                    self.pushbullet_listener = pl2
                    await self.pushlistener_connected(pl2)

                    async for push in pl2:
                        await self.push_received(push, pl2)

            except Exception as ex:
                pass
                print("guitool _listen caught exception", ex)
            finally:
                # if pl2 is not None:
                await self.pushlistener_closed(pl2)

        self.io(_listen())

    def disconnect_button_clicked(self):
        self.status = "Disconnecting from Pushbullet..."
        self.io(self.pushbullet_listener.close())

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
                self.tk(self.lb_device.delete, 0, tk.END)
                for dev in self.devices_in_listbox:
                    self.tk(self.lb_device.insert, tk.END, str(dev.nickname))
                self.status = "Loaded {} devices".format(len(self.devices_in_listbox))

            except Exception as ex:
                self.tk(self.lb_device.delete, 0, tk.END)
                self.status = "Error retrieving devices: {}".format(ex)
                raise ex
            finally:
                self.tk(self.btn_load_devices.configure, state=tk.NORMAL)

        # asyncio.run_coroutine_threadsafe(_load(), self.ioloop)
        self.io(_load())

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

    async def pushlistener_connected(self, listener: LiveStreamListener):
        self.status = "Connected to Pushbullet"
        try:
            me = await self.pushbullet.async_get_user()
            self.status = "Connected to Pushbullet: {}".format(me.get("name"))

        except Exception as ex:
            # print("To include image support: pip install pillow")
            pass
        finally:
            self.tk(self.btn_connect.configure, state=tk.DISABLED)
            self.tk(self.btn_disconnect.configure, state=tk.NORMAL)

    async def pushlistener_closed(self, listener: LiveStreamListener):
        # print_function_name()
        self.status = "Disconnected from Pushbullet"
        self.tk(self.btn_connect.configure, state=tk.NORMAL)
        self.tk(self.btn_disconnect.configure, state=tk.DISABLED)

    async def push_received(self, p: dict, listener: LiveStreamListener):
        # print("Push received:", p)
        push_type = p.get("type")
        if push_type == "push":
            push_type = "ephemeral"
        prev = self.pushes_var.get()
        prev += "Type: {}\n{}\n\n".format(push_type, pprint.pformat(p))
        self.tk(self.pushes_var.set, prev)

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
                        me = await self.pushbullet.async_get_user()
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
                                self.tk(self.lbl_photo.configure, image=photo)
                                self.lbl_photo.image_ref = photo  # Save for garbage collection protection
                                self.log.info("Loaded user image from url {}".format(image_url))

                    except Exception as ex:
                        # print(ex)
                        print("To include image support: pip install pillow")
                        # ex.with_traceback()
                        # raise ex

                asyncio.get_event_loop().create_task(_load_pic())

        except Exception as e:
            self.status = "Invalid API key: {}".format(api_key)
            self.tk(self.lbl_photo.configure, image="")
            self.lbl_photo.image_ref = None
            raise e


def main():
    tk1 = tk.Tk()
    _ = GuiToolApp(tk1)
    tk1.mainloop()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Quitting")
        pass
