# -*- coding: utf-8 -*-
"""The non-asyncio version of the Pushbullet clas.
If you are not using the asyncio capabilities of this package,
it is recommended that you stick with Igor's own package."""

import datetime
import json
import logging
import os
from typing import List, Iterator, Optional

import requests  # pip install requests

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
                salt=self.get_user()["iden"].encode("ASCII"),  # If using asyncpushbullet, this is synchronous still
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
        self.get_user()  # Will trigger an invalid key if invalid

    def close(self):
        if self._session is not None:
            self._session.close()
            self._session = None

    @property
    def session(self) -> requests.Session:
        """ Creates the http session upon first use. """
        session = self._session
        if session is None:
            self.log.info("Creating requests-based, synchronous session.")
            if self.__class__.__name__ == "AsyncPushbullet":
                self.log.debug(
                    "A requests-based, synchronous session is being created from AsyncPushbullet--" +
                    "did you mean to use async functions?")

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
            self.log.error("{} {}".format(code, err_msg))
            raise HttpError(code, err_msg, msg)

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

    def _objects_iter(self, url, item_name,
                      limit: int = None,
                      page_size: int = None,
                      active_only: bool = True,
                      modified_after: float = None) -> Iterator[dict]:
        """Returns an iterator that retrieves objects from pushbullet."""

        items_returned = 0
        get_more = True
        params = {}
        if page_size is not None:
            params["limit"] = page_size
        if active_only is not None:
            params["active"] = "true" if active_only else "false"
        if modified_after is not None:
            params["modified_after"] = str(modified_after)

        while get_more:
            print("Retrieving...", end="", flush=True)
            # msg = await self._async_get_data(url, params=params)
            msg = self._get_data(url, params=params)
            items_this_round = msg.get(item_name, [])
            print("{} items".format(len(items_this_round)), flush=True)

            for item in items_this_round:
                yield item
                items_returned += 1
                if limit is not None and 0 < limit <= items_returned:
                    get_more = False
                    break  # out of for loop

            # Presence of cursor indicates more data is available
            params["cursor"] = msg.get("cursor")
            if not params["cursor"]:
                get_more = False
            # else:
            #     print("ARBITRARY DELAY FOR DEBUGGING")
            #     sleep(1)

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

    #
    # # ################
    # # Cached Data
    # # - This data is retained locally rather than querying Pushbullet each time.
    #
    # def refresh(self):
    #     self._load_user_info()
    #     # self._load_devices()
    #     # self._load_chats()
    #     # self._load_channels()
    #     self.get_pushes(limit=1)
    #
    # # @property
    # # def user_info(self) -> dict:
    # #     """ :rtype: dict """
    # #     if self._user_info is None:
    # #         self._load_user_info()
    # #     return self._user_info
    # #
    # # def _load_user_info(self):
    # #     self._user_info = self._get_data(self.ME_URL)

    # ################
    # User
    #

    def get_user(self):
        self._user_info = self._get_data(self.ME_URL)
        return self._user_info

    # ################
    # Device
    #

    def devices_iter(self,
                     limit: int = None,
                     page_size: int = None,
                     active_only: bool = None,
                     modified_after: float = None) -> Iterator[Device]:
        """Returns an iterator that retrieves devices from pushbullet.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: iterator
        :rtype: Iterator[Device]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.DEVICES_URL
        item_name = "devices"
        for x in self._objects_iter(url, item_name, limit=limit, page_size=page_size,
                                    active_only=active_only, modified_after=modified_after):
            yield Device(self, x)

    def get_devices(self, flush_cache: bool = False) -> List[Device]:
        """Returns a list of Device objects known by Pushbullet.

        This returns immediately with a cached copy, if available.
        If not available, or if flush_cache=True, then a call will be made to
        Pushbullet.com to retrieve a fresh list.

        :param bool flush_cache: whether or not to flush the cache first
        :return: list of Device objects
        :rtype: List[Device]
        """
        items = self._devices
        if items is None or flush_cache:
            items = [x for x in self.devices_iter(limit=None,
                                                  page_size=100,
                                                  active_only=True)]
            self._devices = items
        return items

    def get_device(self, nickname: str = None, iden: str = None) -> Optional[Device]:
        """
        Attempts to retrieve a device based on the given nickname or iden.
        First looks in the cached copy of the data and then refreshes the
        cache once if the device is not found.
        Returns None if the device is still not found.

        :param str nickname: the nickname of the device to find
        :param str iden: the device_iden of the device to find
        :return: the Device that was found or None if not found
        :rtype: Device
        """
        _ = self.get_devices()  # If no cached copy, create one

        def _get():
            if nickname:
                return next((x for x in self._devices if x.nickname == nickname), None)
            elif iden:
                return next((x for x in self._devices if x.device_iden == iden), None)

        x = _get()
        if x is None:
            self.log.debug("Device {} not found in cache.  Refreshing.".format(nickname or iden))
            _ = self.get_devices(flush_cache=True)  # Refresh cache once
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
        self._devices = None
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
        self._devices = None
        yield new_device

    def remove_device(self, device: Device):
        msg = self._delete_data("{}/{}".format(self.DEVICES_URL, device.device_iden))
        return msg

    # ################
    # Chat
    #

    def chats_iter(self,
                   limit: int = None,
                   page_size: int = None,
                   active_only: bool = None,
                   modified_after: float = None) -> Iterator[Chat]:
        """Returns an iterator that retrieves chats from pushbullet.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: iterator
        :rtype: Iterator[Chat]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.CHATS_URL
        item_name = "chats"
        for x in self._objects_iter(url, item_name, limit=limit, page_size=page_size,
                                    active_only=active_only, modified_after=modified_after):
            yield Chat(self, x)

    def get_chats(self, flush_cache: bool = False) -> List[Chat]:
        """Returns a list of Chat objects known by Pushbullet.

        This returns immediately with a cached copy, if available.
        If not available, or if flush_cache=True, then a call will be made to
        Pushbullet.com to retrieve a fresh list.

        :param bool flush_cache: whether or not to flush the cache first
        :return: list of Chat objects
        :rtype: List[Device]
        """
        items = self._chats
        if items is None or flush_cache:
            items = [x for x in self.chats_iter(limit=None,
                                                page_size=100,
                                                active_only=True)]
            self._chats = items
        return items

    def get_chat(self, email: str) -> Optional[Chat]:
        """
        Attempts to retrieve a device based on the given nickname or iden.
        First looks in the cached copy of the data and then refreshes the
        cache once if the device is not found.
        Returns None if the device is still not found.

        :param str email: the email of the chat contact to find
        :return: the Chat that was found or None if not found
        :rtype: Chat
        """
        _ = self.get_devices()  # If no cached copy, create one

        def _get():
            return next((x for x in self._chats if x.email == email), None)

        x = _get()
        if x is None:
            self.log.debug("Chat {} not found in cache.  Refreshing.".format(email))
            _ = self.get_chats(flush_cache=True)  # Refresh cache once
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
        yield new_chat

    def remove_chat(self, chat: Chat) -> dict:
        msg = self._delete_data("{}/{}".format(self.CHATS_URL, chat.iden))
        self._chats = None  # flush cache
        return msg

    # ################
    # Channel
    #

    def channels_iter(self,
                      limit: int = None,
                      page_size: int = None,
                      active_only: bool = None,
                      modified_after: float = None) -> Iterator[Channel]:
        """Returns an iterator that retrieves channels from pushbullet.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: iterator
        :rtype: Iterator[Channel]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.CHANNELS_URL
        item_name = "channels"
        for x in self._objects_iter(url, item_name, limit=limit, page_size=page_size,
                                    active_only=active_only, modified_after=modified_after):
            yield Channel(self, x)

    def get_channels(self, flush_cache: bool = False) -> List[Channel]:
        """Returns a list of Channel objects known by Pushbullet.

        This returns immediately with a cached copy, if available.
        If not available, or if flush_cache=True, then a call will be made to
        Pushbullet.com to retrieve a fresh list.

        :param bool flush_cache: whether or not to flush the cache first
        :return: list of Channel objects
        :rtype: List[Channel]
        """
        items = self._channels
        if items is None or flush_cache:
            items = [x for x in self.channels_iter(limit=None,
                                                   page_size=100,
                                                   active_only=True)]
            self._channels = items
        return items

    def get_channel(self, channel_tag: str) -> Optional[Channel]:
        """
        Attempts to retrieve a channel based on the given channel_tag.
        First looks in the cached copy of the data and then refreshes the
        cache once if the channel is not found.
        Returns None if the channel is still not found.

        This API call is vague in the pushbullet documentation, but it
        appears to refer to only those channels managed by the user--this
        may not apply to very many users of pushbullet.

        :param str nickname: the nickname of the device to find
        :param str iden: the device_iden of the device to find
        :return: the Device that was found or None if not found
        :rtype: Device
        """
        _ = self.get_channels()  # If no cached copy, create one

        def _get():
            return next((x for x in self._channels if x.channel_tag == channel_tag), None)

        x = _get()
        if x is None:
            self.log.debug("Channel {} not found in cache.  Refreshing.".format(channel_tag))
            _ = self.get_channels(flush_cache=True)  # Refresh cache once
            x = _get()
        return x

    def get_channel_info(self, channel_tag: str, no_recent_pushes: bool = None) -> Optional[Channel]:
        """Returns information about the channel tag requested.

        This queries the list of all channels provided through pushbullet, not
        just those managed by the user.

        """
        params = {"tag": str(channel_tag)}
        if no_recent_pushes:
            params["no_recent_pushes"] = "true"
        try:
            msg = self._get_data(self.CHANNEL_INFO_URL, params=params)
        except HttpError as he:
            if he.code == 400:  # That channel does not exist
                return None
        else:
            return Channel(self, msg)

    # ################
    # Subscriptions
    #

    def subscriptions_iter(self,
                           limit: int = None,
                           page_size: int = None,
                           active_only: bool = None,
                           modified_after: float = None) -> Iterator[Subscription]:
        """Returns an iterator that retrieves subscriptions from pushbullet.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: iterator
        :rtype: Iterator[Subscription]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.SUBSCRIPTIONS_URL
        item_name = "subscriptions"
        for x in self._objects_iter(url, item_name, limit=limit, page_size=page_size,
                                    active_only=active_only, modified_after=modified_after):
            yield Subscription(self, x)

    def get_subscriptions(self, flush_cache: bool = False) -> List[Subscription]:
        """Returns a list of Subscription objects known by Pushbullet.

        This returns immediately with a cached copy, if available.
        If not available, or if flush_cache=True, then a call will be made to
        Pushbullet.com to retrieve a fresh list.

        :param bool flush_cache: whether or not to flush the cache first
        :return: list of Subscription objects
        :rtype: List[Subscription]
        """
        items = self._subscriptions
        if items is None or flush_cache:
            items = [x for x in self.subscriptions_iter(limit=None,
                                                        page_size=100,
                                                        active_only=True)]
            self._subscriptions = items
        return items

    def get_subscription(self, channel_tag: str = None) -> Optional[Subscription]:
        """
        Attempts to retrieve a subscription based on the given channel tag.
        First looks in the cached copy of the data and then refreshes the
        cache once if the device is not found.
        Returns None if the device is still not found.

        :param str channel_tag: the channel tag of the subscription to find
        :return: the Subscription that was found or None if not found
        :rtype: Subscription
        """
        _ = self.get_subscriptions()  # If no cached copy, create one

        def _get():
            return next((x for x in self._subscriptions
                         if x.channel and x.channel.channel_tag == channel_tag), None)

        x = _get()
        if x is None:
            self.log.debug("Subscription to {} not found in cache.  Refreshing.".format(channel_tag))
            _ = self.get_subscriptions(flush_cache=True)  # Refresh cache once
            x = _get()
        return x

    def new_subscription(self, channel_tag: str) -> Subscription:
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
        new_subscr = Subscription(self, msg)
        self._subscriptions = None
        yield new_subscr

    def edit_subscription(self, subscr_iden: str, muted: bool) -> Subscription:
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
        new_subscr = Subscription(self, msg)
        self._subscriptions = None
        yield new_subscr

    def remove_subscription(self, subscr_iden: str) -> dict:
        msg = self._delete_data("{}/{}".format(self.SUBSCRIPTIONS_URL, subscr_iden))
        return msg

    # ################
    # Pushes
    #

    def pushes_iter(self,
                    limit: int = None,
                    page_size: int = None,
                    active_only: bool = None,
                    modified_after: float = None) -> Iterator[dict]:
        """Returns an iterator that retrieves pushes from pushbullet.

        :param limit: maximum number to return (Default: 10, None means unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: iterator
        :rtype: Iterator[dict]
        """
        limit = 10 if limit is None else limit  # Default value
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.PUSH_URL
        item_name = "pushes"
        for x in self._objects_iter(url, item_name, limit=limit, page_size=page_size,
                                    active_only=active_only, modified_after=modified_after):
            modified = x.get("modified", 0)
            if modified > self.most_recent_timestamp:
                self.most_recent_timestamp = modified
            yield x

    def get_pushes(self,
                   limit: int = None,
                   page_size: int = None,
                   active_only: bool = None,
                   modified_after: float = None) -> List[dict]:
        """Returns a list of pushes with the given filters applied"""
        return [x for x in self.pushes_iter(limit=limit,
                                            page_size=page_size,
                                            active_only=active_only,
                                            modified_after=modified_after)]

    def get_new_pushes(self, limit: int = None, active_only: bool = True) -> [dict]:
        return self.get_pushes(modified_after=self.most_recent_timestamp,
                               limit=limit, active_only=active_only)

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
        _ = self.get_user()  # cache user info
        gen = self._push_sms_generator(device, number, message)
        xfer = next(gen)  # Prep http params
        data = xfer.get("data")
        xfer["msg"] = self._post_data(self.EPHEMERALS_URL, data=json.dumps(data))
        resp = next(gen)  # Post process response
        return resp

    def _push_sms_generator(self, device: Device, number: str, message: str):
        user_info = self._user_info or self.get_user()  # Fallback use synchronous IO
        data = {
            "type": "push",
            "push": {
                "type": "messaging_extension_reply",
                "package_name": "com.pushbullet.android",
                "source_user_iden": user_info['iden'],
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
