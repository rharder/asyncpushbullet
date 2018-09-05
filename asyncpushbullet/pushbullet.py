# -*- coding: utf-8 -*-
"""The non-asyncio version of the Pushbullet clas.
If you are not using the asyncio capabilities of this package,
it is recommended that you stick with Igor's own package."""

import datetime
import json
import logging
import os
import pprint
from typing import List

import requests

from ._compat import standard_b64encode
from .channel import Channel
from .chat import Chat
from .device import Device
from .errors import InvalidKeyError, HttpError
from .filetype import get_file_type
from .subscription import Subscription


class NoEncryptionModuleError(Exception):
    def __init__(self, msg):
        super(NoEncryptionModuleError, self).__init__(
            "cryptography is required for end-to-end encryption support and could not be imported: " + msg + "\nYou can install it by running 'pip install cryptography'")


class Pushbullet:
    V2_PREFIX_URL = "https://api.pushbullet.com/v2/"
    DEVICES_URL = "https://api.pushbullet.com/v2/devices"
    CHATS_URL = "https://api.pushbullet.com/v2/chats"
    CHANNELS_URL = "https://api.pushbullet.com/v2/channels"
    SUBSCRIPTIONS_URL = "https://api.pushbullet.com/v2/subscriptions"
    CHANNEL_INFO_URL = "https://api.pushbullet.com/v2/channel-info"
    ME_URL = "https://api.pushbullet.com/v2/users/me"
    PUSH_URL = "https://api.pushbullet.com/v2/pushes"
    UPLOAD_REQUEST_URL = "https://api.pushbullet.com/v2/upload-request"
    EPHEMERALS_URL = "https://api.pushbullet.com/v2/ephemerals"
    TRANSFER_SH_URL = "https://transfer.sh/"

    def __init__(self, api_key: str = None, encryption_password: str = None, proxy: str = None, verify_ssl=None):
        self.api_key = api_key
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self._session = None  # type: requests.Session
        self._json_header = {'Content-Type': 'application/json'}
        self.most_recent_timestamp = 0.0  # type: float
        self.proxy = None if proxy is None or str(proxy).strip() == "" else str(proxy)
        self.verify_ssl = verify_ssl

        self._user_info = None  # type: dict
        self._devices = None  # type: List[Device]
        self._chats = None  # type: List[Chat]
        self._channels = None  # type: List[Channel]
        self._subscriptions = None  # type: List[Subscription]

        self._encryption_key = None
        if encryption_password:
            try:
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.backends import default_backend
                from cryptography.hazmat.primitives import hashes
            except ImportError as e:
                raise NoEncryptionModuleError(str(e))

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.user_info["iden"].encode("ASCII"),
                iterations=30000,
                backend=default_backend()
            )
            self._encryption_key = kdf.derive(encryption_password.encode("UTF-8"))

    def __enter__(self):
        self.verify_key()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def verify_key(self):
        """
        Triggers a call to Pushbullet.com that will throw an
        InvalidKeyError if the key is not valid.
        """
        self._load_user_info()  # Will trigger an invalid key if invalid

    def close(self):
        if self._session is not None:
            self._session.close()
            self._session = None

    @property
    def session(self) -> requests.Session:
        """ Creates the http session upon first use. """

        # raise Exception("Why is sync pushbullet session being called instead of async?")  # debugging line

        session = self._session
        if session is None:
            # Set up session
            session = requests.Session()
            session.auth = (self.api_key, "")
            session.headers.update(self._json_header)
            session.proxies.update(dict(https=self.proxy))
            self._session = session

            # Find most recent push's timestamp
            self.get_pushes(limit=1)  # Find timestamp of most recent push

        return session

    # ################
    # IO Methods
    #

    def _http(self, func, url: str, **kwargs) -> dict:
        """ All HTTP transactions funnel through here. """

        # If uploading a file, temporarily remove JSON header
        if "files" in kwargs:
            del self.session.headers["Content-Type"]

        # SSL?
        if self.verify_ssl is not None and "verify" not in kwargs:
            kwargs["verify"] = self.verify_ssl

        # Do HTTP
        try:
            resp = func(url, **kwargs)
        finally:
            self.session.headers.update(self._json_header)  # Put JSON header back

        code = resp.status_code
        msg = None  # type: dict
        try:
            if code != 204:  # No content
                msg = resp.json()
        except:
            pass
        finally:
            if msg is None:
                msg = resp.content

        return self._interpret_response(resp.status_code, resp.headers, msg)

    def _interpret_response(self, code: int, headers: dict, msg: dict):
        """ Interpret the HTTP response headers, raise exceptions, etc. """
        # print_function_name()
        if code == 400:
            err_msg = "Bad request."
            raise HttpError(code, err_msg, msg)

        elif code == 401:
            err_msg = "Invalid API Key: {}".format(self.api_key)
            raise InvalidKeyError(code, err_msg, msg)

        elif code == 403:
            err_msg = "Forbidden: the access token is not valid for that request."
            raise HttpError(code, err_msg, msg)

        elif code == 404:
            err_msg = "Not found."
            raise HttpError(code, err_msg, msg)

        elif code == 429:
            epoch = int(headers.get("X-Ratelimit-Reset", 0))
            epoch_time = datetime.datetime.fromtimestamp(epoch).strftime('%c')
            err_msg = "Too Many Requests. You have been ratelimited until {}".format(epoch_time)
            self.log.error("{} {}".format(code, msg))
            raise HttpError(code, err_msg)

        elif code // 100 == 5:  # 5xx
            err_msg = "Server error on pushbullet.com."
            raise HttpError(code, err_msg, msg)

        elif code not in (200, 204):  # 200 OK, 204 Empty response (file upload)
            err_msg = "Unknown error."
            raise HttpError(code, err_msg, msg)

        elif not isinstance(msg, dict):
            msg = {"raw": msg}

        return msg

    def _get_data(self, url: str, **kwargs) -> dict:
        """ HTTP GET """
        msg = self._http(self.session.get, url, **kwargs)
        return msg

    def _get_data_with_pagination(self, url: str, item_name: str, **kwargs) -> dict:
        """ Performs a GET on a list that Pushbullet may paginate. """
        gen = self._get_data_with_pagination_generator(url, item_name, **kwargs)
        xfer = next(gen)  # Prep params
        msg = {}
        while xfer.get("get_more", False):
            args = xfer.get("kwargs", {})  # type: dict
            xfer["msg"] = self._get_data(url, **args)
            msg = next(gen)
        return msg

    def _get_data_with_pagination_generator(self, url: str, item_name: str, **kwargs):
        msg = {}
        items = []
        limit = kwargs.get("params", {}).get("limit")
        xfer = {"kwargs": kwargs, "get_more": True}
        empty_rounds_in_a_row = 0
        while xfer["get_more"]:
            yield xfer  # Do IO

            msg = xfer.get("msg", {})  # IO response
            items_this_round = msg.get(item_name, [])
            items += items_this_round

            # Check for empty data being returned.
            # This seems to happen if the last transaction on the pushbullet
            # account was not push-related, such as adding or removing a device.
            # If too many empty rounds come in a row, something is wrong, and we
            # don't want to get stuck in an infinite loop.
            if len(items_this_round) == 0:
                empty_rounds_in_a_row += 1
            else:
                empty_rounds_in_a_row = 0

            if empty_rounds_in_a_row > 10:
                # I cannot find any documentation on this, but sometimes no data is returned,
                # but the cursor is still provided and after asking enough times, suddenly
                # data arrives.
                self.log.warning("Received {} rounds of empty data from pusbhullet -- something is not right.".format(
                    empty_rounds_in_a_row))
                xfer["get_more"] = False

            # Need subsequent calls to get rest of data?
            # if "cursor" in msg and len(items_this_round) > 0 and (limit is None or len(items) < limit):
            if "cursor" in msg and (limit is None or len(items) < limit):
                if "params" in xfer["kwargs"]:
                    xfer["kwargs"]["params"].update({"cursor": msg["cursor"]})
                else:
                    xfer["kwargs"]["params"] = {"cursor": msg["cursor"]}
                    # xfer["kwargs"]["params"] = {"cursor": msg["cursor"]}
                    self.log.info("Paging for more {} ({})".format(item_name, len(items)))
            else:
                xfer["get_more"] = False
        msg[item_name] = items[:limit]  # Cut down to limit
        yield msg

    def _post_data(self, url: str, **kwargs) -> dict:
        """ HTTP POST """
        msg = self._http(self.session.post, url, **kwargs)
        return msg

    def _delete_data(self, url: str, **kwargs) -> dict:
        """ HTTP DELETE """
        msg = self._http(self.session.delete, url, **kwargs)
        return msg

    def _push(self, data: dict) -> dict:
        """ Helper for generic push """
        msg = self._post_data(Pushbullet.PUSH_URL, data=json.dumps(data))
        return msg

    @staticmethod
    def _recipient(device: Device = None, chat: Chat = None,
                   email: str = None, channel: Channel = None) -> dict:
        data = dict()

        if device:
            data["device_iden"] = device.device_iden
            if device.push_token:
                data["push_token"] = device.push_token
        elif chat:
            data["email"] = chat.email
        elif email:
            data["email"] = email
        elif channel:
            data["channel_tag"] = channel.channel_tag

        return data

    # ################
    # Cached Data
    # - This data is retained locally rather than querying Pushbullet each time.

    def refresh(self):
        self._load_user_info()
        # self._load_devices()
        # self._load_chats()
        # self._load_channels()
        self.get_pushes(limit=1)

    @property
    def user_info(self) -> dict:
        """ :rtype: dict """
        if self._user_info is None:
            self._load_user_info()
        return self._user_info

    def _load_user_info(self):
        self._user_info = self._get_data(self.ME_URL)

    # ################
    # Device
    #

    @property
    def devices(self) -> [Device]:
        """ :rtype: [Device] """
        if self._devices is None:
            self._load_devices()
        return self._devices

    def _load_devices(self):
        self._devices = []
        msg = self._get_data_with_pagination(self.DEVICES_URL, "devices", params={"active": "true"})
        device_list = msg.get('devices', [])
        for device_info in device_list:
            if device_info.get("active"):
                d = Device(self, device_info)
                self._devices.append(d)
        self.log.info("Found {} active devices".format(len(self._devices)))

    def get_device(self, nickname: str = None, iden: str = None) -> Device:
        """
        Attempts to retrieve a device based on the given nickname or iden.
        First looks in the cached copy of the data and then refreshes the
        cache once if the device is not found.
        Returns None if the device is still not found.
        """
        if self._devices is None:
            self._devices = []

        def _get():
            if nickname:
                return next((x for x in self._devices if x.nickname == nickname), None)
            elif iden:
                return next((x for x in self._devices if x.device_iden == iden), None)

        x = _get()
        if x is None:
            self.log.debug("Device {} not found in cache.  Refreshing.".format(nickname or iden))
            self._load_devices()  # Refresh cache once
            x = _get()
        return x

    def new_device(self, nickname: str, manufacturer: str = None,
                   model: str = None, icon: str = "system") -> Device:
        gen = self._new_device_generator(nickname, manufacturer=manufacturer, model=model, icon=icon)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data(self.DEVICES_URL, data=json.dumps(data))
        resp = next(gen)  # Post process response
        return resp

    def _new_device_generator(self, nickname: str, manufacturer: str = None,
                              model: str = None, icon: str = "system"):
        """
        Note about this "xxx_generator" construct:
        To avoid duplication of code in the synchronous Pushbullet and
        asynchronous AsyncPushbullet, the generators are used in the
        pre- and post-manipulation of the data.  For example the
        pre-manipulation activity is generally setting up the data
        fields as required by the Pushbullet.com API.
        As a result the xxx_generator functions typically have two parts
        to them where they are prepping data and then processing
        a response.

        The xfer object is used to pass data back and forth to/from
        the generator and the calling function.

        Yeah, it's weird, it's advanced, it's tricky.
        And it enables reuse of code across sync and asyncio style functions!
        """
        data = {"nickname": nickname, "icon": icon}
        data.update({k: v for k, v in
                     (("model", model), ("manufacturer", manufacturer)) if v is not None})
        xfer = {"data": data}
        yield xfer  # Hand control back in order to conduct IO

        msg = xfer.get('msg', {})
        new_device = Device(self, msg)
        self.devices.append(new_device)
        yield new_device

    def edit_device(self, device: Device, nickname: str = None,
                    model: str = None, manufacturer: str = None,
                    icon: str = None, has_sms: bool = None) -> dict:
        gen = self._edit_device_generator(device, nickname=nickname, model=model,
                                          manufacturer=manufacturer, icon=icon, has_sms=has_sms)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data("{}/{}".format(self.DEVICES_URL, device.device_iden), data=json.dumps(data))
        return next(gen)  # Post process response

    def _edit_device_generator(self, device: Device, nickname: str = None,
                               model: str = None, manufacturer: str = None,
                               icon: str = None, has_sms: bool = None):
        data = {k: v for k, v in
                (("nickname", nickname or device.nickname), ("model", model),
                 ("manufacturer", manufacturer), ("icon", icon),
                 ("has_sms", has_sms)) if v is not None}
        if "has_sms" in data:
            data["has_sms"] = str(data["has_sms"]).lower()
        xfer = {"data": data}
        yield xfer

        msg = xfer.get('msg', {})
        new_device = Device(self, msg)
        self.devices[self.devices.index(device)] = new_device
        yield new_device

    def remove_device(self, device: Device):
        msg = self._delete_data("{}/{}".format(self.DEVICES_URL, device.device_iden))
        return msg

    # ################
    # Chat
    #

    @property
    def chats(self) -> [Chat]:
        """ :rtype: [Chat] """
        if self._chats is None:
            self._load_chats()
        return self._chats

    def _load_chats(self):
        print("SYNCHRONOUS VERSION OF _load_chats CALLED")
        self._chats = []
        msg = self._get_data_with_pagination(self.CHATS_URL, "chats", params={"active": "true"})
        chat_list = msg.get('chats', [])
        for chat_info in chat_list:
            if chat_info.get("active"):
                c = Chat(self, chat_info)
                self.chats.append(c)
        self.log.info("Found {} active chats".format(len(self._chats)))

    def get_chat(self, email: str) -> Chat:
        if self._chats is None:
            self._chats = []

        def _get():
            return next((x for x in self._chats if x.email == email), None)

        x = _get()
        if x is None:
            self.log.debug("Chat {} not found in cache.  Refreshing.".format(email))
            self._load_chats()  # Refresh cache once
            x = _get()
        return x

    def new_chat(self, email: str) -> Chat:
        gen = self._new_chat_generator(email)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data(self.CHATS_URL, data=json.dumps(data))
        return next(gen)  # Post process response

    def _new_chat_generator(self, email):
        data = {"email": email}
        xfer = {"data": data}
        yield xfer

        msg = xfer.get('msg', {})
        new_chat = Chat(self, msg)
        # self.chats.append(new_chat)
        self._chats = None  # flush cache
        yield new_chat

    def edit_chat(self, chat: Chat, muted: bool = False) -> Chat:
        gen = self._edit_chat_generator(chat, muted)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data("{}/{}".format(self.CHATS_URL, chat.iden), data=json.dumps(data))
        return next(gen)  # Post process response

    def _edit_chat_generator(self, chat, muted=False):
        data = {"muted": "true" if muted else "false"}
        xfer = {"data": data}
        yield xfer

        msg = xfer.get('msg', {})
        new_chat = Chat(self, msg)
        self._chats = None  # flush cache
        # if self._chats is not None:
        #     self._chats[self.chats.index(chat)] = new_chat
        yield new_chat

    def remove_chat(self, chat: Chat) -> dict:
        msg = self._delete_data("{}/{}".format(self.CHATS_URL, chat.iden))
        self._chats = None  # flush cache
        return msg

    # ################
    # Channel
    #

    @property
    def channels(self) -> [Channel]:
        """ :rtype: [Channel] """
        if self._channels is None:
            self._load_channels()
        return self._channels

    def _load_channels(self):
        print("SYNCHRONOUS VERSION OF _load_channels CALLED")
        self._channels = []
        msg = self._get_data_with_pagination(self.CHANNELS_URL, "channels", params={"active": "true"})
        channel_list = msg.get('channels', [])
        for channel_info in channel_list:
            if channel_info.get("active"):
                c = Channel(self, channel_info)
                self.channels.append(c)
        self.log.info("Found {} active channels".format(len(self._channels)))

    def get_channel(self, channel_tag: str) -> Channel:
        if self._channels is None:
            self._channels = []

        def _get():
            return next((x for x in self._channels if x.channel_tag == channel_tag), None)

        x = _get()
        if x is None:
            self.log.debug("Channel {} not found in cache.  Refreshing.".format(channel_tag))
            self._load_channels()  # Refresh cache once
            x = _get()
        return x

    def get_channel_info(self, channel_tag: str, no_recent_pushes: bool = None):
        params = {"tag": str(channel_tag)}
        if no_recent_pushes:
            params["no_recent_pushes"] = "true"

        try:
            msg = self._get_data(self.CHANNEL_INFO_URL, params=params)
        except HttpError as he:
            if he.code == 400:  # That channel does not exist
                return None
        else:
            return msg

    # ################
    # Subscriptions
    #

    @property
    def subscriptions(self) -> List[dict]:
        """ :rtype: List[dict] """
        if self._subscriptions is None:
            self._load_subscriptions()
        return self._subscriptions

    def _load_subscriptions(self):
        self._subscriptions = []
        msg = self._get_data_with_pagination(self.SUBSCRIPTIONS_URL, "subscriptions", params={"active": "true"})
        subscr_list = msg.get('subscriptions', [])
        for info in subscr_list:
            if info.get("active"):
                self._subscriptions.append(info)
        return self._subscriptions

    def get_subscription(self, channel_tag: str) -> dict:
        """Returns the Subscription to the channel with the given tag, or None if not subscribed to that channel."""
        if self._subscriptions is None:
            self._subscriptions = []

        def _get():
            return next((x for x in self._subscriptions if x.get("channel", {}).get("tag") == channel_tag), None)

        x = _get()
        if x is None:
            self.log.debug("Subscription {} not found in cache.  Refreshing.".format(channel_tag))
            self._load_subscriptions()  # Refresh cache once
            x = _get()
        return x

    def new_subscription(self, channel_tag: str) -> dict:
        gen = self._new_subscription_generator(channel_tag)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data(self.SUBSCRIPTIONS_URL, data=json.dumps(data))
        return next(gen)  # Post process response

    def _new_subscription_generator(self, channel_tag):
        data = {"channel_tag": channel_tag}
        xfer = {"data": data}
        yield xfer

        msg = xfer.get('msg', {})
        new_subscr = msg
        # new_chat = Chat(self, msg)
        if self._subscriptions is not None:
            self._subscriptions.append(new_subscr)
        yield new_subscr

    def edit_subscription(self, subscr_iden: str, muted: bool) -> dict:
        gen = self._edit_subscription_generator(subscr_iden, muted)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = self._post_data("{}/{}".format(self.SUBSCRIPTIONS_URL, subscr_iden), data=json.dumps(data))
        return next(gen)  # Post process response

    def _edit_subscription_generator(self, subscr_iden, muted=False):
        data = {"muted": "true" if muted else "false"}
        xfer = {"data": data}
        yield xfer

        msg = xfer.get('msg', {})
        # new_chat = Chat(self, msg)
        new_subscr = msg
        # self.chats[self.chats.index(chat)] = new_chat
        self._subscriptions = None
        yield new_subscr

    def remove_subscription(self, subscr_iden: str) -> dict:
        msg = self._delete_data("{}/{}".format(self.SUBSCRIPTIONS_URL, subscr_iden))
        return msg

    # ################
    # Pushes
    #

    def get_pushes(self,
                   modified_after: float = None,
                   limit: int = None,
                   filter_inactive: bool = True) -> [dict]:
        # print_function_name()
        gen = self._get_pushes_generator(modified_after=modified_after,
                                         limit=limit, filter_inactive=filter_inactive)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = self._get_data_with_pagination(self.PUSH_URL, "pushes", params=data)
        resp = next(gen)  # Post process response
        return resp

    def _get_pushes_generator(self, modified_after: float = None, limit: int = None,
                              filter_inactive: bool = True):
        # print_function_name(self)
        data = {}
        if modified_after is not None:
            data["modified_after"] = str(modified_after)
        if limit is not None:
            data["limit"] = int(limit)
        if filter_inactive:
            data['active'] = "true"
        else:
            data['active'] = "false"
        xfer = {"data": data}
        yield xfer  # Do IO

        msg = xfer.get('msg', {})
        pushes_list = msg.get("pushes", [])
        if len(pushes_list) > 0 and pushes_list[0].get('modified', 0) > self.most_recent_timestamp:
            self.most_recent_timestamp = pushes_list[0].get('modified')

        if self.log.isEnabledFor(logging.DEBUG):
            self.log.debug("Retrieved {} push{}: {}".format(len(pushes_list),
                                                            "" if len(pushes_list) == 1 else "es",
                                                            pprint.pformat(pushes_list)))
        yield pushes_list

    def get_new_pushes(self, limit: int = None, filter_inactive: bool = True) -> [dict]:
        return self.get_pushes(modified_after=self.most_recent_timestamp,
                               limit=limit, filter_inactive=filter_inactive)

    def dismiss_push(self, iden: str) -> dict:
        if type(iden) is dict and "iden" in iden:
            iden = getattr(iden, "iden")  # In case user passes entire push
        data = {"dismissed": "true"}
        msg = self._post_data("{}/{}".format(self.PUSH_URL, iden), data=json.dumps(data))
        return msg

    def delete_push(self, iden: str) -> dict:
        if type(iden) is dict and "iden" in iden:
            iden = getattr(iden, "iden")  # In case user passes entire push
        msg = self._delete_data("{}/{}".format(self.PUSH_URL, iden))
        return msg

    def delete_pushes(self) -> dict:
        msg = self._delete_data(self.PUSH_URL)
        return msg

    def push_note(self, title: str, body: str, device: Device = None, chat: Chat = None,
                  email: str = None, channel: Channel = None) -> dict:
        data = {"type": "note", "title": title, "body": body}
        data.update(Pushbullet._recipient(device, chat, email, channel))
        resp = self._push(data)
        return resp

    def push_link(self, title: str, url: str, body: str = None, device: Device = None,
                  chat: Chat = None, email: str = None, channel: Channel = None) -> dict:
        data = {"type": "link", "title": title, "url": url, "body": body}
        data.update(Pushbullet._recipient(device, chat, email, channel))
        resp = self._push(data)
        return resp

    def push_sms(self, device: Device, number: str, message: str) -> dict:
        gen = self._push_sms_generator(device, number, message)
        xfer = next(gen)  # Prep http params
        data = xfer.get("data")
        xfer["msg"] = self._post_data(self.EPHEMERALS_URL, data=json.dumps(data))
        resp = next(gen)  # Post process response
        return resp

    def _push_sms_generator(self, device: Device, number: str, message: str):
        data = {
            "type": "push",
            "push": {
                "type": "messaging_extension_reply",
                "package_name": "com.pushbullet.android",
                "source_user_iden": self.user_info['iden'],
                "target_device_iden": device.device_iden,
                "conversation_iden": number,
                "message": message
            }
        }

        if self._encryption_key:
            data["push"] = {
                "ciphertext": self._encrypt_data(data["push"]),
                "encrypted": "true"
            }

        xfer = {"data": data}
        yield xfer  # Do IO
        yield xfer["msg"]

    def push_ephemeral(self, data) -> dict:
        gen = self._push_ephemeral_generator(data)
        xfer = next(gen)  # Prep http params
        data = xfer.get("data")
        xfer["msg"] = self._post_data(self.EPHEMERALS_URL, data=json.dumps(data))
        resp = next(gen)  # Post process response
        return resp

    def _push_ephemeral_generator(self, payload):
        data = {"type": "push", "push": payload}
        xfer = {"data": data}
        yield xfer  # Do IO
        yield xfer["msg"]

    # ################
    # Files
    #

    def upload_file_to_transfer_sh(self, file_path: str, file_type: str = None) -> dict:
        file_name = os.path.basename(file_path)
        if not file_type:
            file_type = get_file_type(file_path)

        with open(file_path, "rb") as f:
            upload_resp = self._post_data(self.TRANSFER_SH_URL, files={"file": f})

        file_url = upload_resp.get("raw", b'').decode("ascii")
        msg = {"file_name": file_name,
               "file_type": file_type,
               "file_url": file_url}

        return msg

    def upload_file(self, file_path: str, file_type: str = None) -> dict:
        gen = self._upload_file_generator(file_path, file_type=file_type)
        xfer = next(gen)  # Prep request params

        # data = json.dumps(xfer["data"])
        data = xfer["data"]
        xfer["msg"] = self._post_data(self.UPLOAD_REQUEST_URL, data=json.dumps(data))
        next(gen)  # Prep upload params

        with open(file_path, "rb") as f:
            xfer["msg"] = self._post_data(str(xfer["upload_url"]), files={"file": f})

        return next(gen)  # Post process response

    def _upload_file_generator(self, file_path: str, file_type: str = None):
        file_name = os.path.basename(file_path)
        if not file_type:
            file_type = get_file_type(file_path)
        data = {"file_name": file_name, "file_type": file_type}
        xfer = {"data": data}
        yield xfer  # Request upload

        msg = xfer["msg"]
        xfer["upload_url"] = str(msg.get("upload_url"))  # Upload location
        file_url = str(msg.get("file_url"))  # Final destination for downloading
        file_type = str(msg.get("file_type"))  # What PB thinks is the filetype
        yield xfer  # Conduct upload

        return_msg = {"file_type": file_type, "file_url": file_url, "file_name": file_name}
        self.log.info("File uploaded: {}".format(return_msg))
        yield return_msg

    def push_file(self, file_name: str, file_url: str, file_type: str,
                  body: str = None, title: str = None, device: Device = None,
                  chat: Chat = None, email: str = None,
                  channel: Channel = None) -> dict:
        gen = self._push_file_generator(file_name, file_url, file_type, body=body, title=title,
                                        device=device, chat=chat, email=email, channel=channel)
        xfer = next(gen)  # Prep http params
        data = xfer.get("data")
        xfer["msg"] = self._push(data)
        return next(gen)  # Post process response

    def _push_file_generator(self, file_name, file_url, file_type, body=None, title=None, device=None, chat=None,
                             email=None,
                             channel=None):
        data = {"type": "file", "file_type": file_type, "file_url": file_url, "file_name": file_name}
        if body:
            data["body"] = body
        if title:
            data["title"] = title
        data.update(Pushbullet._recipient(device, chat, email, channel))
        xfer = {"data": data}
        yield xfer  # Do IO
        yield xfer.get("msg", {})

    def _encrypt_data(self, data):
        assert self._encryption_key

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        iv = os.urandom(12)
        encryptor = Cipher(
            algorithms.AES(self._encryption_key),
            modes.GCM(iv),
            backend=default_backend()
        ).encryptor()

        ciphertext = encryptor.update(json.dumps(data).encode("UTF-8")) + encryptor.finalize()
        ciphertext = b"1" + encryptor.tag + iv + ciphertext
        return standard_b64encode(ciphertext).decode("ASCII")

    def _decrypt_data(self, data):
        assert self._encryption_key

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        from binascii import a2b_base64

        key = self._encryption_key
        encoded_message = a2b_base64(data)

        version = encoded_message[0:1]
        tag = encoded_message[1:17]
        initialization_vector = encoded_message[17:29]
        encrypted_message = encoded_message[29:]

        if version != b"1":
            raise Exception("Invalid Version")

        cipher = Cipher(algorithms.AES(key),
                        modes.GCM(initialization_vector, tag),
                        backend=default_backend())
        decryptor = cipher.decryptor()

        decrypted = decryptor.update(encrypted_message) + decryptor.finalize()
        decrypted = decrypted.decode()

        return decrypted
