# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import pprint
from typing import Dict

# from asyncpushbullet import Pushbullet
from .helpers import use_appropriate_encoding, reify


class Chat:
    CHAT_ATTRIBUTES = ("iden", "active", "created", "modified", "muted", "with")
    CHAT_WITH_ATTRIBUTES = ("email", "email_normalized", "iden", "image_url", "type", "name")

    def __init__(self, account, chat_info):
        self._account = account
        self.chat_info = chat_info  # type: Dict
        self.with_info = chat_info.get("with", dict())  # type: Dict

        # Transfer attributes
        for attr in self.CHAT_ATTRIBUTES:
            setattr(self, attr, chat_info.get(attr))

        # Transfer attributes of "with" ie, the contact on the other end
        for attr in self.CHAT_WITH_ATTRIBUTES:
            attr_name = "with_{}".format(attr)
            setattr(self, attr_name, self.with_info.get(attr))

    def _push(self, data):
        data["email"] = self.with_email
        return self._account._push(data)

    @use_appropriate_encoding
    def __str__(self):
        return "Chat('{0}' <{1}>)".format(self.with_name, self.with_email_normalized)


    @use_appropriate_encoding
    def __repr__(self):
        attr_map = {k: self.__getattribute__(k) for k in self.CHAT_ATTRIBUTES}
        attr_str = pprint.pformat(attr_map)
        _str = "Chat('{}' <{}> :\n{})".format(self.with_name, self.with_email_normalized, attr_str)
        # _str = "Chat('{}',\n{})".format(self.nickname or "nameless (iden: {})"
        #                                   .format(self.iden), attr_str)
        return _str

    @reify
    def iden(self):
        return getattr(self, "iden")

    @reify
    def active(self):
        return getattr(self, "active")

    @reify
    def created(self):
        return getattr(self, "created")

    @reify
    def modified(self):
        return getattr(self, "modified")

    @reify
    def muted(self):
        return getattr(self, "muted")

    @reify
    def with_email(self):
        return getattr(self, "with_email")

    @reify
    def with_email_normalized(self):
        return getattr(self, "with_email_normalized")

    @reify
    def with_iden(self):
        return getattr(self, "with_iden")

    @reify
    def with_image_url(self):
        return getattr(self, "with_image_url")

    @reify
    def with_type(self):
        return getattr(self, "with_type")

    @reify
    def with_name(self):
        return getattr(self, "with_name")
