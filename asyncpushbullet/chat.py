from __future__ import unicode_literals

from typing import Dict

from .helpers import use_appropriate_encoding


class Chat:
    CHAT_ATTRIBUTES = ("active", "created", "modified", "muted", "with")
    CHAT_WITH_ATTRIBUTES = ("email", "email_normalized", "iden", "image_url", "type", "name")

    def __init__(self, account, chat_info):
        self._account = account
        self._chat_info = chat_info
        self.iden = chat_info.get("iden")

        # Transfer attributes
        for attr in self.CHAT_ATTRIBUTES:
            setattr(self, attr, chat_info.get(attr))

        # Transfer attributes of "with" ie, the contact on the other end
        self.with_info = chat_info.get("with", dict())  # type: Dict
        for attr in self.CHAT_WITH_ATTRIBUTES:
            attr_name = "with_{}".format(attr)
            setattr(self, attr_name, self.with_info.get(attr))

    def _push(self, data):
        data["email"] = self.with_email
        return self._account._push(data)

    @use_appropriate_encoding
    def __str__(self):
        return "Chat('{0}' <{1}>)".format(self.with_name, self.with_email_normalized)

    # @property
    # def active(self):
    #     return getattr(self, "active")
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
    # def muted(self):
    #     return getattr(self, "muted")
    #
    # @property
    # def with_email(self):
    #     return getattr(self, "with_email")
    #
    # @property
    # def with_email_normalized(self):
    #     return getattr(self, "with_email_normalized")
    #
    # @property
    # def with_iden(self):
    #     return getattr(self, "with_iden")
    #
    # @property
    # def with_image_url(self):
    #     return getattr(self, "with_image_url")
    #
    # @property
    # def with_type(self):
    #     return getattr(self, "with_type")
    #
    # @property
    # def with_name(self):
    #     return getattr(self, "with_name")
