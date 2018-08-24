from __future__ import unicode_literals

import pprint
import warnings

from .helpers import use_appropriate_encoding


class Device:
    DEVICE_ATTRIBUTES = ("push_token", "app_version", "fingerprint", "created", "modified",
                         "active", "nickname", "generated_nickname", "manufacturer", "icon",
                         "model", "has_sms", "key_fingerprint")

    def __init__(self, account, device_info):
        self._account = account
        self.device_iden = device_info.get("iden")
        self.device_info = device_info
        if not device_info.get("icon", None):
            device_info["icon"] = "system"
        for attr in self.DEVICE_ATTRIBUTES:
            setattr(self, attr, device_info.get(attr))

    def push_note(self, title, body):
        data = {"type": "note", "title": title, "body": body}
        return self._push(data)

    def push_address(self, name, address):
        warnings.warn("Address push type is removed. This push will be sent as note.")
        return self.push_note(name, address)

    def push_list(self, title, items):
        warnings.warn("List push type is removed. This push will be sent as note.")
        return self.push_note(title, ",".join(items))

    def push_link(self, title, url, body=None):
        data = {"type": "link", "title": title, "url": url, "body": body}
        return self._push(data)

    def push_file(self, file_name, file_url, file_type, body=None, title=None):
        return self._account.push_file(file_name, file_url, file_type, body=body, title=title, device=self)

    def _push(self, data):
        data["device_iden"] = self.device_iden
        if getattr(self, "push_token") is not None:
            data["push_token"] = self.push_token
            print("Including push token {} in push coming from device {}".format(self.push_token, self))
        else:
            print("Skipping push token")
        return self._account._push(data)

    @use_appropriate_encoding
    def __str__(self):
        _str = "Device('{}')".format(self.nickname or "nameless (iden: {})"
                                     .format(self.device_iden))
        return _str

    def __repr__(self):
        attr_map = {k: self.__getattribute__(k) for k in self.DEVICE_ATTRIBUTES}
        # attr_str = ", ".join(["{}={}".format(k,v) for k,v in attr_map.items()])
        attr_str = pprint.pformat(attr_map)
        _str = "Device('{}',\n{})".format(self.nickname or "nameless (iden: {})"
                                          .format(self.device_iden), attr_str)
        return _str

    # @property
    # def push_token(self):
    #     return getattr(self, "push_token")
    #
    # @property
    # def app_version(self):
    #     return getattr(self, "app_version")
    #
    # @property
    # def fingerprint(self):
    #     return getattr(self, "fingerprint")
    #
    # @property
    # def created(self):
    #     return getattr(self, "created")
    #
    # @property
    # def modified(self):
    #     return getattr(self, "modified")
    #
    # @property
    # def active(self):
    #     return getattr(self, "active")
    #
    # @property
    # def nickname(self):
    #     return getattr(self, "nickname")
    #
    # @property
    # def generated_nickname(self):
    #     return getattr(self, "generated_nickname")
    #
    # @property
    # def manufacturer(self):
    #     return getattr(self, "manufacturer")
    #
    # @property
    # def icon(self):
    #     return getattr(self, "icon")
    #
    # @property
    # def model(self):
    #     return getattr(self, "model")
    #
    # @property
    # def has_sms(self):
    #     return getattr(self, "has_sms")
    #
    # @property
    # def key_fingerprint(self):
    #     return getattr(self, "key_fingerprint")
