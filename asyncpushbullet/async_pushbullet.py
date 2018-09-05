# -*- coding: utf-8 -*-
"""Asyncio version of Pushbullet class."""

import asyncio
import os
import sys
from typing import List, AsyncIterator, Optional

import aiohttp

from asyncpushbullet import Device, PushbulletError, Subscription
from asyncpushbullet.channel import Channel
from asyncpushbullet.chat import Chat
from asyncpushbullet.errors import HttpError
from asyncpushbullet.filetype import get_file_type
from asyncpushbullet.tqio import tqio
from .pushbullet import Pushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"


class AsyncPushbullet(Pushbullet):
    def __init__(self, api_key: str = None, verify_ssl: bool = None,
                 # loop: asyncio.AbstractEventLoop = None,
                 **kwargs):
        Pushbullet.__init__(self, api_key, **kwargs)
        self.loop = None  # type: asyncio.BaseEventLoop #= loop or asyncio.get_event_loop()

        # self._aio_sessions = {}  # type: Dict[asyncio.AbstractEventLoop, aiohttp.ClientSession]
        self._aio_session = None  # type: aiohttp.ClientSession
        self.verify_ssl = verify_ssl

    async def __aenter__(self):
        await self.async_verify_key()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.async_close()

    async def async_verify_key(self):
        """
        Triggers a call to Pushbullet.com that will throw an
        InvalidKeyError if the key is not valid.
        """
        _ = await self.aio_session()

    async def aio_session(self) -> aiohttp.ClientSession:
        """Returns an open aiohttp.ClientSession with API key verified and timestamp
         of latest push updated.

         The session is cached, so aio_session can be called (awaited) as often
         as needed with no overhead.

         Raises a PushbulletError if something goes wrong.
         """
        session = self._aio_session

        if session is None or session.closed:
            self.loop = asyncio.get_event_loop()

            # print("Session is None, creating new one")
            headers = {"Access-Token": self.api_key}

            aio_connector = None  # type: aiohttp.TCPConnector
            if self.verify_ssl is not None and self.verify_ssl is False:
                self.log.info("SSL/TLS verification disabled")
                aio_connector = aiohttp.TCPConnector(verify_ssl=False)

            session = aiohttp.ClientSession(headers=headers, connector=aio_connector)  # , trust_env=True)
            self.log.debug("Created new session: {}".format(session))
            self._aio_session = session

            try:
                # This will recursively call aio_session() but that's OK
                # because self._aio_session caches it until we determine
                # if the key is valid in the line below.
                # Other purpose: Establish a timestamp for the most recent push
                _ = await self.async_get_pushes(limit=1, active_only=False)  # May throw invalid key error here

            except Exception as ex:
                await session.close()
                self._aio_session = None
                if isinstance(ex, PushbulletError):
                    raise ex
                else:
                    tb = sys.exc_info()[2]
                    raise PushbulletError(ex).with_traceback(tb) from ex

        return session

    async def async_close(self):
        """Closes only the session on the current event loop and the synchronous session in the super class"""
        super().close()  # synchronous version in superclass
        if self._aio_session:
            await self._aio_session.close()
            self._aio_session = None
            self.loop = None

    def close_all_threadsafe(self):
        """Closes all sessions, which may be on different event loops.
        This method is NOT awaited--because there may be different loops involved."""
        super().close()  # Synchronous closer for superclass
        if self._aio_session:
            assert self.loop is not None
            asyncio.run_coroutine_threadsafe(self.async_close(), loop=self.loop)

    # ################
    # IO Methods
    #

    async def _async_http(self, aiohttp_func, url: str, **kwargs) -> dict:

        try:
            async with aiohttp_func(url + "", proxy=self.proxy, **kwargs) as resp:  # Do HTTP
                code = resp.status
                msg = None
                try:
                    if code != 204:  # 204 would be "No content"
                        msg = await resp.json()
                except:
                    pass
                finally:
                    if msg is None:
                        msg = await resp.read()

                return self._interpret_response(code, resp.headers, msg)

        except Exception as ex:
            if isinstance(ex, PushbulletError):
                raise ex
            else:
                tb = sys.exc_info()[2]
                raise PushbulletError(ex).with_traceback(tb) from ex

    async def _async_get_data(self, url: str, **kwargs) -> dict:
        session = await self.aio_session()
        msg = await self._async_http(session.get, url, **kwargs)
        return msg

    async def _async_objects_iter(self, url, item_name,
                                  limit: int = None,
                                  page_size: int = None,
                                  active_only: bool = True,
                                  modified_after: float = None) -> AsyncIterator[dict]:
        """Returns an async iterator that retrieves objects from pushbullet."""

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
            msg = await self._async_get_data(url, params=params)
            items_this_round = msg.get(item_name, [])
            print("{} items".format(len(items_this_round)), flush=True)

            for item in items_this_round:
                yield item
                items_returned += 1
                if limit is not None and items_returned >= limit:
                    get_more = False
                    break  # out of for loop

            # Presence of cursor indicates more data is available
            params["cursor"] = msg.get("cursor")
            if not params["cursor"]:
                get_more = False
            # else:
            #     print("ARBITRARY DELAY FOR DEBUGGING")
            #     await asyncio.sleep(1)

    async def _async_post_data(self, url: str, **kwargs) -> dict:
        session = await self.aio_session()
        # kwargs["timeout"] = None  # Don't know why this was there
        msg = await self._async_http(session.post, url, **kwargs)
        return msg

    async def _async_delete_data(self, url: str, **kwargs) -> dict:
        session = await self.aio_session()
        msg = await self._async_http(session.delete, url, **kwargs)

        return msg

    async def _async_push(self, data: dict, **kwargs) -> dict:
        msg = await self._async_post_data(self.PUSH_URL, data=data, **kwargs)
        return msg

    # ################
    # User
    #

    async def async_get_user(self):
        self._user_info = await self._async_get_data(self.ME_URL)
        return self._user_info

    # ################
    # Device
    #

    async def async_devices_iter(self,
                                 limit: int = None,
                                 page_size: int = None,
                                 active_only: bool = None,
                                 modified_after: float = None) -> AsyncIterator[Device]:
        """Returns an async iterator that retrieves devices from pushbullet.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: AsyncIterator[Device]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.DEVICES_URL
        item_name = "devices"
        async for x in self._async_objects_iter(url, item_name, limit=limit, page_size=page_size,
                                                active_only=active_only, modified_after=modified_after):
            yield Device(self, x)

    async def async_get_devices(self, flush_cache: bool = False) -> List[Device]:
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
            items = [x async for x in self.async_devices_iter(limit=None,
                                                              page_size=100,
                                                              active_only=True)]
            self._devices = items
        return items

    async def async_get_device(self, nickname: str = None, iden: str = None) -> Optional[Device]:
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
        _ = await self.async_get_devices()  # If no cached copy, create one

        def _get():
            if nickname:
                return next((x for x in self._devices if x.nickname == nickname), None)
            elif iden:
                return next((x for x in self._devices if x.device_iden == iden), None)

        x = _get()
        if x is None:
            self.log.debug("Device {} not found in cache.  Refreshing.".format(nickname or iden))
            _ = await self.async_get_devices(flush_cache=True)  # Refresh cache once
            x = _get()
        return x

    async def async_new_device(self, nickname: str, manufacturer: str = None,
                               model: str = None, icon: str = "system") -> Device:
        gen = self._new_device_generator(nickname, manufacturer=manufacturer, model=model, icon=icon)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = await self._async_post_data(self.DEVICES_URL, data=data)
        resp = next(gen)  # Post process response
        return resp

    async def async_edit_device(self, device: Device, nickname: str = None,
                                model: str = None, manufacturer: str = None,
                                icon: str = None, has_sms: bool = None) -> Device:
        gen = self._edit_device_generator(device, nickname=nickname, model=model,
                                          manufacturer=manufacturer, icon=icon, has_sms=has_sms)
        xfer = next(gen)
        data = xfer["data"]
        xfer["msg"] = await self._async_post_data("{}/{}".format(self.DEVICES_URL, device.device_iden), data=data)
        return next(gen)

    async def async_remove_device(self, device: Device) -> dict:
        data = await self._async_delete_data("{}/{}".format(self.DEVICES_URL, device.device_iden))
        return data

    # ################
    # Chat
    #

    async def async_chats_iter(self,
                               limit: int = None,
                               page_size: int = None,
                               active_only: bool = None,
                               modified_after: float = None) -> AsyncIterator[Chat]:
        """Returns an async iterator that retrieves chats from pushbullet.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: AsyncIterator[Chat]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.CHATS_URL
        item_name = "chats"
        async for x in self._async_objects_iter(url, item_name, limit=limit, page_size=page_size,
                                                active_only=active_only, modified_after=modified_after):
            yield Chat(self, x)

    async def async_get_chats(self, flush_cache: bool = False) -> List[Chat]:
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
            items = [x async for x in self.async_chats_iter(limit=None,
                                                            page_size=100,
                                                            active_only=True)]
            self._chats = items
        return items

    async def async_get_chat(self, email: str) -> Optional[Chat]:
        """
        Attempts to retrieve a device based on the given nickname or iden.
        First looks in the cached copy of the data and then refreshes the
        cache once if the device is not found.
        Returns None if the device is still not found.

        :param str email: the email of the chat contact to find
        :return: the Chat that was found or None if not found
        :rtype: Chat
        """
        _ = await self.async_get_devices()  # If no cached copy, create one

        def _get():
            return next((x for x in self._chats if x.email == email), None)

        x = _get()
        if x is None:
            self.log.debug("Chat {} not found in cache.  Refreshing.".format(email))
            _ = await self.async_get_chats(flush_cache=True)  # Refresh cache once
            x = _get()
        return x

    async def async_new_chat(self, email: str) -> Chat:
        gen = self._new_chat_generator(email)
        xfer = next(gen)  # Prep http params
        data = xfer.get("data", {})
        xfer["msg"] = await self._async_post_data(self.CHATS_URL, data=data)
        return next(gen)  # Post process response

    async def async_edit_chat(self, chat: Chat, muted: bool = False) -> Chat:
        gen = self._edit_chat_generator(chat, muted)
        xfer = next(gen)
        data = xfer.get('data', {})
        xfer["msg"] = await self._async_post_data("{}/{}".format(self.CHATS_URL, chat.iden), data=data)
        return next(gen)

    async def async_remove_chat(self, chat: Chat) -> dict:
        msg = await self._async_delete_data("{}/{}".format(self.CHATS_URL, chat.iden))
        return msg

    # ################
    # Channel
    #

    async def async_channels_iter(self,
                                  limit: int = None,
                                  page_size: int = None,
                                  active_only: bool = None,
                                  modified_after: float = None) -> AsyncIterator[Channel]:
        """Returns an async iterator that retrieves channels from pushbullet.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: AsyncIterator[Channel]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.CHANNELS_URL
        item_name = "channels"
        async for x in self._async_objects_iter(url, item_name, limit=limit, page_size=page_size,
                                                active_only=active_only, modified_after=modified_after):
            yield Channel(self, x)

    async def async_get_channels(self, flush_cache: bool = False) -> List[Channel]:
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
            items = [x async for x in self.async_channels_iter(limit=None,
                                                               page_size=100,
                                                               active_only=True)]
            self._channels = items
        return items

    async def async_get_channel(self, channel_tag: str) -> Optional[Channel]:
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
        _ = await self.async_get_channels()  # If no cached copy, create one

        def _get():
            return next((x for x in self._channels if x.channel_tag == channel_tag), None)

        x = _get()
        if x is None:
            self.log.debug("Channel {} not found in cache.  Refreshing.".format(channel_tag))
            _ = await self.async_get_channels(flush_cache=True)  # Refresh cache once
            x = _get()
        return x

    async def async_get_channel_info(self, channel_tag: str, no_recent_pushes: bool = None) -> Optional[Channel]:
        """Returns information about the channel tag requested.

        This queries the list of all channels provided through pushbullet, not
        just those managed by the user.

        """
        params = {"tag": str(channel_tag)}
        if no_recent_pushes:
            params["no_recent_pushes"] = "true"
        try:
            msg = await self._async_get_data(self.CHANNEL_INFO_URL, params=params)
        except HttpError as he:
            if he.code == 400:  # That channel does not exist
                return None
        else:
            return Channel(self, msg)

    # ################
    # Subscriptions
    #

    async def async_subscriptions_iter(self,
                                       limit: int = None,
                                       page_size: int = None,
                                       active_only: bool = None,
                                       modified_after: float = None) -> AsyncIterator[Subscription]:
        """Returns an async iterator that retrieves subscriptions from pushbullet.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: AsyncIterator[Subscription]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.SUBSCRIPTIONS_URL
        item_name = "subscriptions"
        async for x in self._async_objects_iter(url, item_name, limit=limit, page_size=page_size,
                                                active_only=active_only, modified_after=modified_after):
            yield Subscription(self, x)

    async def async_get_subscriptions(self, flush_cache: bool = False) -> List[Subscription]:
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
            items = [x async for x in self.async_subscriptions_iter(limit=None,
                                                                    page_size=100,
                                                                    active_only=True)]
            self._subscriptions = items
        return items

    async def async_get_subscription(self, channel_tag: str = None) -> Optional[Subscription]:
        """
        Attempts to retrieve a subscription based on the given channel tag.
        First looks in the cached copy of the data and then refreshes the
        cache once if the device is not found.
        Returns None if the device is still not found.

        :param str channel_tag: the channel tag of the subscription to find
        :return: the Subscription that was found or None if not found
        :rtype: Subscription
        """
        _ = await self.async_get_subscriptions()  # If no cached copy, create one

        def _get():
            return next((x for x in self._subscriptions
                         if x.channel and x.channel.channel_tag == channel_tag), None)

        x = _get()
        if x is None:
            self.log.debug("Subscription to {} not found in cache.  Refreshing.".format(channel_tag))
            _ = await self.async_get_subscriptions(flush_cache=True)  # Refresh cache once
            x = _get()
        return x

    async def async_new_subscription(self, channel_tag: str) -> dict:
        gen = self._new_subscription_generator(channel_tag)
        xfer = next(gen)  # Prep http params
        data = xfer.get("data", {})
        xfer["msg"] = await self._async_post_data(self.SUBSCRIPTIONS_URL, data=data)
        return next(gen)  # Post process response

    async def async_edit_subscription(self, subscr_iden: str, muted: bool) -> dict:
        gen = self._edit_subscription_generator(subscr_iden, muted)
        xfer = next(gen)
        data = xfer.get('data', {})
        xfer["msg"] = await self._async_post_data("{}/{}".format(self.SUBSCRIPTIONS_URL, subscr_iden), data=data)
        return next(gen)

    async def async_remove_subscription(self, subscr_iden: str) -> dict:
        msg = await self._async_delete_data("{}/{}".format(self.SUBSCRIPTIONS_URL, subscr_iden))
        return msg

    # ################
    # Pushes
    #

    async def async_pushes_iter(self,
                                limit: int = 10,
                                page_size: int = None,
                                active_only: bool = None,
                                modified_after: float = None) -> AsyncIterator[dict]:
        """Returns an async iterator that retrieves pushes from pushbullet.

        :param limit: maximum number to return (Default: 10, None means unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com (Default: 10)
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: AsyncIterator[dict]
        """
        page_size = 10 if page_size is None else page_size  # Default value
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        url = self.PUSH_URL
        item_name = "pushes"
        async for x in self._async_objects_iter(url, item_name, limit=limit, page_size=page_size,
                                                active_only=active_only, modified_after=modified_after):
            modified = x.get("modified", 0)
            if modified > self.most_recent_timestamp:
                self.most_recent_timestamp = modified
            yield x

    async def async_get_pushes(self,
                               limit: int = None,
                               page_size: int = None,
                               active_only: bool = None,
                               modified_after: float = None) -> List[dict]:
        """Returns a list of pushes with the given filters applied"""
        return [x async for x in self.async_pushes_iter(limit=limit,
                                                        page_size=page_size,
                                                        active_only=active_only,
                                                        modified_after=modified_after)]

    async def async_get_new_pushes(self, limit: int = None, active_only: bool = True):
        return await self.async_get_pushes(modified_after=self.most_recent_timestamp,
                                           limit=limit, active_only=active_only)

    async def async_dismiss_push(self, iden: str) -> dict:
        if type(iden) is dict and "iden" in iden:
            iden = getattr(iden, "iden")  # In case user passes entire push
        data = {"dismissed": "true"}
        msg = await self._async_post_data("{}/{}".format(self.PUSH_URL, iden), data=data)
        return msg

    async def async_delete_push(self, iden: str) -> dict:
        if type(iden) is dict and "iden" in iden:
            iden = getattr(iden, "iden")  # In case user passes entire push
        msg = await self._async_delete_data("{}/{}".format(self.PUSH_URL, iden))
        return msg

    async def async_delete_pushes(self) -> dict:
        msg = await self._async_delete_data(self.PUSH_URL)
        return msg

    async def async_push_note(self, title: str,
                              body: str,
                              device: Device = None,
                              chat: Chat = None,
                              email: str = None,
                              channel: Channel = None) -> dict:
        data = {"type": "note", "title": title, "body": body}
        data.update(Pushbullet._recipient(device=device,
                                          chat=chat,
                                          email=email,
                                          channel=channel))
        msg = await self._async_push(data)
        return msg

    async def async_push_link(self, title: str, url: str, body: str = None,
                              device: Device = None,
                              chat: Chat = None,
                              email: str = None,
                              channel: Channel = None) -> dict:
        data = {"type": "link", "title": title, "url": url, "body": body}
        data.update(Pushbullet._recipient(device=device,
                                          chat=chat,
                                          email=email,
                                          channel=channel))
        msg = await self._async_push(data)
        return msg

    async def async_push_sms(self, device: Device, number: str, message: str) -> dict:
        gen = self._push_sms_generator(device, number, message)
        xfer = next(gen)  # Prep params
        data = xfer.get("data")
        xfer["msg"] = await self._async_post_data(self.EPHEMERALS_URL, json=data)
        return next(gen)  # Post process

    async def async_push_ephemeral(self, payload) -> dict:
        gen = self._push_ephemeral_generator(payload)
        xfer = next(gen)  # Prep params
        data = xfer.get("data")
        # I have not been able to determine why this aiohttp post command
        # must have a json=.. parameter instead of data=.. like push_note. RH
        xfer["msg"] = await self._async_post_data(self.EPHEMERALS_URL, json=data)
        return next(gen)  # Post process

    # ################
    # Files
    #

    async def async_upload_file_to_transfer_sh(self, file_path: str, file_type: str = None,
                                               show_progress: bool = True) -> dict:
        """Uploads a file to the https://transfer.sh service.

        This returns the same dictionary data as the async_upload_file function, which
        uploads to the pushbullet service.
        """
        file_name = os.path.basename(file_path)
        if not file_type:
            file_type = get_file_type(file_path)

        if show_progress:
            with tqio(file_path) as f:
                upload_resp = await self._async_post_data(self.TRANSFER_SH_URL, data={"file": f})
        else:
            with open(file_path, "rb") as f:
                upload_resp = await self._async_post_data(self.TRANSFER_SH_URL, data={"file": f})

        file_url = upload_resp.get("raw", b'').decode("ascii")
        msg = {"file_name": file_name,
               "file_type": file_type,
               "file_url": file_url}

        return msg

    async def async_upload_file(self, file_path: str, file_type: str = None,
                                show_progress: bool = True) -> dict:
        """
        Uploads a file to pushbullet storage and returns a dict with information
        about how the uploaded file:

        {"file_type": file_type, "file_url": file_url, "file_name": file_name}

        :param file_path:
        :param file_type:
        :return:
        """
        gen = self._upload_file_generator(file_path, file_type=file_type)

        xfer = next(gen)  # Prep request params

        data = xfer["data"]
        xfer["msg"] = await self._async_post_data(self.UPLOAD_REQUEST_URL, data=data)
        next(gen)  # Prep upload params

        if show_progress:
            with tqio(file_path) as f:
                xfer["msg"] = await self._async_post_data(xfer["upload_url"], data={"file": f})
        else:
            with open(file_path, "rb") as f:
                xfer["msg"] = await self._async_post_data(xfer["upload_url"], data={"file": f})

        resp = next(gen)
        return resp

    async def async_push_file(self, file_name: str, file_url: str, file_type: str,
                              body: str = None, title: str = None,
                              device: Device = None,
                              chat: Chat = None,
                              email: str = None,
                              channel: Channel = None) -> dict:
        gen = self._push_file_generator(file_name, file_url, file_type, body=body, title=title,
                                        device=device, chat=chat, email=email, channel=channel)
        xfer = next(gen)
        data = xfer.get("data")
        xfer["msg"] = await self._async_push(data)
        return next(gen)
