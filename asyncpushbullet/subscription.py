# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import pprint

from .channel import Channel
from .helpers import use_appropriate_encoding, reify


class Subscription:
    SUBSCRIPTION_ATTRIBUTES = ("iden", "active", "created", "modified", "muted")

    def __init__(self, account, subscription_info):
        self._account = account
        self.subscription_info = subscription_info
        self.channel = Channel(account, subscription_info.get("channel"))  # type: Channel

        # Transfer attributes
        for attr in self.SUBSCRIPTION_ATTRIBUTES:
            setattr(self, attr, subscription_info.get(attr))


    @use_appropriate_encoding
    def __str__(self):
        return "Subscription({})".format(str(self.channel))

    @use_appropriate_encoding
    def __repr__(self):
        attr_map = {k: self.__getattribute__(k) for k in self.SUBSCRIPTION_ATTRIBUTES}
        attr_str = pprint.pformat(attr_map)
        _str = "Subscription({}".format(repr(self.channel))
        _str += ",\n{}".format(attr_str)
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
