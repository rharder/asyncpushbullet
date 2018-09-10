"""
Handles saving preferences between occurrences of running a script.
Source: https://github.com/rharder/handy
"""

import os
import shelve  # For Prefs class
import sys

import appdirs  # pip install appdirs


class Prefs:
    """
    Handles saving preferences between occurrences of running the script.
    """

    def __init__(self, app_name, app_author):
        self.app_name = app_name
        self.app_author = app_author
        self.memory_backup = {}
        self.config_file = Prefs.__create_config_file(app_name, app_author)
        # print(self.config_file)

    def get(self, key, default=None):
        """
        Returns a value from the saved preferences.

        Based on the string key, the value will be returned.  You can pass a default value as a second parameter,
        which will be returned if a saved value cannot be found for that key.  If no default is provided, None
        will be returned in such a case.
        :param str key: The key to look up
        :param default: Default value if key is not found
        :return: The saved value or the default if not found
        """
        mem = self.__memory()
        val = default
        if key in mem:
            val = mem[key]
        return val

    def set(self, key, val):
        """
        Saves a value in the preferences.

        Based on the string key, the value will be saved in the preferences.  The function will return the
        value as well, which can help with embedding the set function in a larger expression.
        :param str key: The key to save under
        :param val: The value to save
        :return: The value
        """
        mem = self.__memory()
        mem[key] = val
        try:
            mem.close()
        except:
            # print("error closing")
            pass
        return val

    def __memory(self):
        """
        Returns a dictionary-like object for reading/writing preferences.

        If possible this will be a saved prefs representation from the 'shelve' module, but it will return a
        regular dictionary if that fails.  If the regular dictionary is returned, then this Prefs class will work
        during the current runtime, but nothing will be saved.
        :return: A dictionary-like object for reading/writing preferences.
        """
        try:
            return shelve.open(self.config_file)
        except Exception as e:
            print(self.__class__.__name__, e)
            return self.memory_backup

    @staticmethod
    def __create_config_file(app_name, app_author):
        """
        Tries to find a folder and file to save preferences.

        :param app_name: Author of the app
        :param app_author: Name of the app
        :return: A config file to use for saving prefs or None if unable
        """
        config_file = None
        # Try the platform-appropriate preferences folder
        config_dir = appdirs.user_config_dir(app_name, app_author)
        if not os.path.isdir(config_dir):
            os.makedirs(config_dir)
        config_file = os.path.join(config_dir, "config")

        # Try users home directory
        if config_file is None:
            home_dir = os.path.expanduser("~")
            config_dir = os.path.join(home_dir, ".{}".format(app_name))
            if not os.path.isdir(config_dir):
                try:
                    os.makedirs(config_dir)
                    config_file = os.path.join(config_dir, "config")
                except:
                    print("Could not make preferences folder at {}".format(
                        config_dir), file=sys.stderr)

        if config_file is None:
            print("Could not make a preferences folder.  Settings will not be saved.", file=sys.stderr)

        return config_file
        # end class Prefs

