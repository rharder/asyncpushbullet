#!/usr/bin/env python3
"""
A collection of functions and classes to help with tkinter.
Source: https://github.com/rharder/handy
"""
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import scrolledtext

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"
__date__ = "10 Oct 2017"
__license__ = "Public Domain"



def bind_tk_var_to_tk_attribute(widget, attr_name, tkvar):
    """
    Helper function to bind an arbitrary tk widget attribute to a tk.xxxVar.

    Example:

        window = tk.Tk()
        var = tk.StringVar()
        label = tk.Label(window, text="Change My Background")
        label.pack()
        bind_tk_var_to_tk_attribute(label, "bg", var)
        var.set("light blue")
        window.mainloop()

    Equivalently calls the function:

        label.configure({"bg": "light blue"})

    :param widget: the tk widget to be affected
    :param attr_name: the name of the attribute to bind
    :param tkvar: the variable to bind to
    """
    tkvar.trace("w", lambda _, __, ___, v=tkvar: widget.configure({attr_name: v.get()}))


def bind_tk_var_to_method(func, tkvar):
    """
    Helper function to bind an arbitrary method to a tkvar value.

    Example:

        window = tk.Tk()
        var = tk.StringVar()
        bind_tk_method(window.title, var)
        var.set("My New Title")
        window.mainloop()

    Equivalently calls the function:

        window.title("My New Title")

    :param func: the function to call expecting a single argument
    :param tkvar: the variable to bind to
    """
    tkvar.trace("w", lambda _, __, ___, v=tkvar: func(tkvar.get()))


def bind_tk_var_to_property(obj, prop_name, tkvar):
    """
    Helper function to bind an arbitrary property to a tkvar value.

    Example:

    class Cat:
        def __init__(self):
            self.name = "Tiger"

    window = tk.Tk()
    var = tk.StringVar()
    cat = Cat()
    bind_tk_var_to_property(cat, "name", var)
    var.set("Basement Cat")
    window.mainloop()

    Equivalently sets the property:

        cat.name = "Basement Cat"

    :param obj: the object whose property will be changed
    :param str prop_name: name of the property to change
    :param tk.Variable tkvar: the tk variable from which to get a value
    """
    tkvar.trace("w", lambda _, __, ___, v=tkvar: setattr(obj, prop_name, v.get()))

class FormattableTkStringVar(tk.StringVar):
    """
    An extension of the tk.StringVar that takes a formattable string, eg, "Age: {}" and a list
    of tk.xxxVar objects, and updates the formatted string whenever one of the underlying vars
    is changed.

    Example:

        self.red = tk.IntVar()
        self.green = tk.IntVar()
        self.blue = tk.IntVar()
        self.hex = FormattableTkStringVar("#{:02X}{:02X}{:02X}", [self.red, self.green, self.blue])
        ...
        hex_label = tk.Label(frame, textvariable=self.hex)
    """

    def __init__(self, str_format: str, vars, **kwargs):
        """
        Creates a bindable variable whose string format is up to date with the underlying variables.
        :param str str_format: the string format, eg, "Age: {}"
        :param var_list: the list of tk.xxxVar objects that feed into the string format
        """
        tk.StringVar.__init__(self, **kwargs)
        self._format = str_format
        self._vars = [v for v in vars]

        for v in self._vars:
            v.trace("w", self.var_changed)  # Bind to all underlying vars

        self.update_format()  # Set initial value of formatted string

    def var_changed(self, _, __, ___):
        self.update_format()  # Update with new value

    def update_format(self):
        var_vals = [v.get() for v in self._vars]  # Collect values for all vars
        self.set(self._format.format(*var_vals))  # Format string, unpacking the format(..) arguments


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


class ToggledFrame(tk.LabelFrame):
    """
    Heavily modified from
    http://stackoverflow.com/questions/13141259/expandable-and-contracting-frame-in-tkinter
    """

    def __init__(self, parent, text="", prefs=None, *args, **options):
        try:
            from .prefs import Prefs
        except ImportError:
            print("The Prefs class did not import.  Frame states will not be saved.")
        tk.LabelFrame.__init__(self, parent, text=text, *args, **options)

        self.__title = text
        self.__hidden_text = None
        self.__prefs = prefs  # type: Prefs

        # Data mechanism for show/hide
        name = "ToggledFrame_{}".format(text)
        self.show = tk.IntVar(name=name)
        if self.__prefs:
            self.show.set(self.__prefs.get(name, 1))  # Retrieve from prefs
        else:
            self.show.set(1)  # Default is show

        def __update_show(name, value):
            if self.__prefs:
                self.__prefs.set(name, value)  # Save in prefs
            self.update_gui_based_on_show()  # Update gui

        self.show.trace("w", lambda name, index, mode, v=self.show: __update_show(name, v.get()))

        # This will respond to a click in the frame and toggle the underlying variable
        def frame_clicked(event):
            # print(event)
            self.show.set(int(not bool(self.show.get())))

        self.bind("<Button-1>", frame_clicked)

        # GUI elements
        self.title_frame = ttk.Frame(self)
        self.title_frame.pack(fill="x", expand=1)
        self.subframe = tk.Frame(self, borderwidth=1)
        self.update_gui_based_on_show()

    def clear_subframe(self):
        if self.subframe is not None:
            for widget in self.subframe.winfo_children():
                widget.destroy()
        self.subframe.pack(fill="x", expand=1)
        self.update_gui_based_on_show()

    @property
    def hidden_text(self):
        return self.__hidden_text

    @hidden_text.setter
    def hidden_text(self, value):
        self.__hidden_text = value
        self.update_gui_based_on_show()

    def update_gui_based_on_show(self):
        if bool(self.show.get()):  # Show
            # print("show", self.__title)
            self.subframe.pack(fill="x", expand=1)
            self.config(text=self.__title + " [-]")
        else:  # Hide
            # print("hide", self.__title)
            resp = ""
            if self.hidden_text is not None and self.hidden_text != "":
                resp = " ({})".format(self.hidden_text)
            self.config(text=self.__title + resp)
            self.subframe.forget()


class ToolTip(object):
    """
    create a tooltip for a given widget

    Author: Wayne Brown
    """

    def __init__(self, widget, text='widget info', textvariable=None):
        self.wait_time = 500  # miliseconds
        self.wrap_length = 300  # pixels
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)
        self.id = None
        self.tw = None
        self.textvariable = textvariable  # type: tk.Variable
        if self.textvariable is not None:
            self.textvariable.trace("w", lambda _, __, ___, v=self.textvariable: setattr(self, "text", str(v.get())))
            self.text = str(self.textvariable.get())


    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.wait_time, self.showtip)

    def unschedule(self):
        my_id = self.id
        self.id = None
        if my_id:
            self.widget.after_cancel(my_id)

    def showtip(self, event=None):
        # x = y = 0
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        # creates a toplevel window
        self.tw = tk.Toplevel(self.widget)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(self.tw, text=self.text, justify='left',
                         background="#ffffff", relief='solid', borderwidth=1,
                         wraplength=self.wrap_length)
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()

