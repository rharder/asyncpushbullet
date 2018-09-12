# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import pprint
from typing import Dict

# from asyncpushbullet import Pushbullet
from .helpers import use_appropriate_encoding, reify


class Device:
    DEVICE_ATTRIBUTES = ("push_token", "app_version", "fingerprint", "created", "modified",
                         "active", "nickname", "generated_nickname", "manufacturer", "icon",
                         "model", "has_sms", "key_fingerprint", "iden")

    def __init__(self, account, device_info):
        self._account = account
        self.device_info = device_info  # type: Dict

        if not device_info.get("icon", None):
            device_info["icon"] = "system"

        for attr in self.DEVICE_ATTRIBUTES:
            setattr(self, attr, device_info.get(attr))

    def push_note(self, title, body):
        data = {"type": "note", "title": title, "body": body}
        return self._push(data)

    # def push_address(self, name, address):
    #     warnings.warn("Address push type is removed. This push will be sent as note.")
    #     return self.push_note(name, address)

    # def push_list(self, title, items):
    #     warnings.warn("List push type is removed. This push will be sent as note.")
    #     return self.push_note(title, ",".join(items))

    def push_link(self, title, url, body=None):
        data = {"type": "link", "title": title, "url": url, "body": body}
        return self._push(data)

    def push_file(self, file_name, file_url, file_type, body=None, title=None):
        return self._account.push_file(file_name, file_url, file_type, body=body, title=title, device=self)

    def _push(self, data):
        data["device_iden"] = self.iden
        if getattr(self, "push_token") is not None:
            data["push_token"] = self.push_token
            print("Including push token {} in push coming from device {}".format(self.push_token, self))
        else:
            print("Skipping push token")
        return self._account._push(data)

    @use_appropriate_encoding
    def __str__(self):
        _str = "Device('{}')".format(self.nickname or "nameless (iden: {})"
                                     .format(self.iden))
        return _str

    @use_appropriate_encoding
    def __repr__(self):
        attr_map = {k: self.__getattribute__(k) for k in self.DEVICE_ATTRIBUTES}
        attr_str = pprint.pformat(attr_map)
        _str = str(self) + ",\n{})".format(attr_str)
        return _str

    @reify
    def iden(self):
        return getattr(self, "iden")

    @reify
    def push_token(self):
        return getattr(self, "push_token")

    @reify
    def app_version(self):
        return getattr(self, "app_version")

    @reify
    def fingerprint(self):
        return getattr(self, "fingerprint")

    @reify
    def created(self):
        return getattr(self, "created")

    @reify
    def modified(self):
        return getattr(self, "modified")

    @reify
    def active(self):
        return getattr(self, "active")

    @reify
    def nickname(self):
        return getattr(self, "nickname")

    @reify
    def generated_nickname(self):
        return getattr(self, "generated_nickname")

    @reify
    def manufacturer(self):
        return getattr(self, "manufacturer")

    @reify
    def icon(self):
        return getattr(self, "icon")

    @reify
    def model(self):
        return getattr(self, "model")

    @reify
    def has_sms(self):
        return getattr(self, "has_sms")

    @reify
    def key_fingerprint(self):
        return getattr(self, "key_fingerprint")
