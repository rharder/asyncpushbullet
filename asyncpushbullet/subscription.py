# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import pprint

from asyncpushbullet.channel import Channel
from .helpers import use_appropriate_encoding


class Subscription:
    SUBSCRIPTION_ATTRIBUTES = ("iden", "active", "created", "modified", "muted", "channel")

    def __init__(self, account, subscription_info):
        self._account = account
        self.subscription_info = subscription_info
        self.iden = subscription_info.get("iden")

        # Transfer attributes
        for attr in self.SUBSCRIPTION_ATTRIBUTES:
            setattr(self, attr, subscription_info.get(attr))

        # Special transfer of enclosed channel
        self.channel = Channel(account, subscription_info.get("channel"))

    @use_appropriate_encoding
    def __str__(self):
        return "Subscription({})".format(str(self.channel))

    @use_appropriate_encoding
    def __repr__(self):
        attr_map = {k: self.__getattribute__(k) for k in self.SUBSCRIPTION_ATTRIBUTES}
        attr_str = pprint.pformat(attr_map)
        # _str = "Subscription to ({})".format(repr(self.channel))
        _str = "Subscription({}".format(repr(self.channel))
        _str += ",\n{}".format(attr_str)
        return _str
