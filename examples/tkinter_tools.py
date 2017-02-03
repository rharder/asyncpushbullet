#!/usr/bin/env python3
"""
A collection of functions and classes to help with tkinter.

This is an extract from the tkinter_tools available at http://github.com/rharder/handy
"""
import tkinter as tk
from tkinter import scrolledtext

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"
__date__ = "5 Dec 2016"
__license__ = "Public Domain"


class BindableTextArea(tk.scrolledtext.ScrolledText):
    """
    A multi-line tk widget that is bindable to a tk.StringVar.

    You will need to import ScrolledText like so:

        from tkinter import scrolledtext
    """

    class _SuspendTrace:
        """ Used internally to suspend a trace during some particular operation. """

        def __init__(self, parent):
            self.__parent = parent  # type: BindableTextArea

        def __enter__(self):
            """ At beginning of operation, stop the trace. """
            if self.__parent._trace_id is not None and self.__parent._textvariable is not None:
                self.__parent._textvariable.trace_vdelete("w", self.__parent._trace_id)

        def __exit__(self, exc_type, exc_val, exc_tb):
            """ At conclusion of operation, resume the trace. """
            self.__parent._trace_id = self.__parent._textvariable.trace("w", self.__parent._variable_value_changed)

    def __init__(self, parent, textvariable: tk.StringVar = None, **kwargs):
        tk.scrolledtext.ScrolledText.__init__(self, parent, **kwargs)
        self._textvariable = None  # type: tk.StringVar
        self._trace_id = None
        if textvariable is None:
            self.textvariable = tk.StringVar()
        else:
            self.textvariable = textvariable
        self.bind("<KeyRelease>", self._key_released)

    @property
    def textvariable(self):
        return self._textvariable

    @textvariable.setter
    def textvariable(self, new_var):
        # Delete old trace if we already had a bound textvariable
        if self._trace_id is not None and self._textvariable is not None:
            self._textvariable.trace_vdelete("w", self._trace_id)

        # Set up new textvariable binding
        self._textvariable = new_var
        self._trace_id = self._textvariable.trace("w", self._variable_value_changed)

    def _variable_value_changed(self, _, __, ___):

        # Must be in NORMAL state to respond to delete/insert methods
        prev_state = self["state"]
        self["state"] = tk.NORMAL

        # Replace text
        text = self._textvariable.get()
        self.delete("1.0", tk.END)
        self.insert(tk.END, text)

        # Restore previous state, whatever that was
        self["state"] = prev_state

    def _key_released(self, evt):
        """ When someone types a key, update the bound text variable. """
        text = self.get("1.0", tk.END)
        with BindableTextArea._SuspendTrace(self):  # Suspend trace to avoid infinite recursion
            if self.textvariable:
                self.textvariable.set(text)
