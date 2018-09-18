# -*- coding: utf-8 -*-
"""Asyncio version of Pushbullet class."""

import asyncio
import datetime
import logging
import os
import sys
import traceback
from asyncio import Lock
from pprint import pprint
from typing import List, AsyncIterator, Optional, Callable, Generic, TypeVar

import aiohttp  # pip install aiohttp

from .channel import Channel
from .chat import Chat
from .device import Device
from .errors import HttpError, PushbulletError, InvalidKeyError
from .filetype import get_file_type
from .pushbullet import Pushbullet
from .subscription import Subscription
from .tqio import tqio

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

T = TypeVar('T')  # Used to make PushbulletAsyncIterator a generic


class PushbulletAsyncIterator(AsyncIterator, Generic[T]):
    """Allows for pausable iterators for retrieving objects from pushbullet.com."""

    def __init__(self,
                 parent_pb,
                 _url: str,
                 _item_name: str,
                 _limit: int = None,
                 _page_size: int = None,
                 _active_only: bool = None,
                 _modified_after: float = None,
                 _post_process: Callable = None):
        # Passed args
        self._pb = parent_pb  # type: AsyncPushbullet
        self._url = _url
        self._item_name = _item_name
        self._limit = _limit
        self._page_size = _page_size
        self._active_only = _active_only
        self._modified_after = _modified_after
        self._post_process = _post_process

        # Parameters for HTTP calls
        self._params = {}
        if _page_size is not None:
            self._params["limit"] = _page_size
        if _active_only is not None:
            self._params["active"] = "true" if _active_only else "false"
        if _modified_after is not None:
            self._params["modified_after"] = str(_modified_after)

        # Internal management
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.loop = None  # type: asyncio.BaseEventLoop
        self._paused = False  # type: bool
        self._stop = None  # Instructed to stop or end of iterator
        self._objects = []  # type: List  # Use as FIFO queue of objects retrieved
        self._total_objects_returned = 0  # type: int # Count of objects actually returned by iterator
        self._paused_lock = Lock()  # type: asyncio.Lock  # Used to coordinate pausing on asyncio event loop
        self._get_more = True  # type: bool  # Flag meaning there's more data to retrieve
        self._first_async_run = True  # type: bool  # First chance in an async function, do some housekeeping

        # This is so weird.  When using tkinter, the Lock needs to be saved in a
        # class-level location -- not even object-level -- so that if the application
        # closes when the Lock is acquired, there is not a big ugly exception
        # thrown about an unclosed client session and a task being destroyed.
        # Simply saving a reference to the lock at the AsyncPushbullet class level
        # solves the problem.  Weird.  -RH
        # Now suddenly it's not necessary?  What's going on?
        # self._parent._iterator_locks.append(self._paused_lock)

    @property
    def total_objects_returned(self) -> int:
        """Number of objects that have been returned by the iterator.

        There may be more objects than this retrieved over the network
        but not yet returned/consumed by an async for loop.
        """
        return self._total_objects_returned

    # @property
    # def completed(self) -> bool:
    #     return not self._get_more

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def stopped(self) -> bool:
        return bool(self._stop)

    @property
    def empty(self):
        return not bool(self._objects)

    async def async_pause(self, val: bool = True):
        """Pauses or unpauses the iterator.

        If called without parameters, the pause function pauses the iterator.
        If called with a True/False boolean, it sets the paused state to that value.

        This function is NOT thread safe and must be awaited on the proper event loop.

        :param bool val: the paused state to set (default: True)
        """
        if val and not self._paused:
            self._paused = True
            await self._paused_lock.acquire()
        elif not val:
            self._paused = False
            if self._paused_lock.locked():
                self._paused_lock.release()

    def pause(self, val: bool = True):
        """Pauses or unpauses the iterator.

        If called without parameters, the pause function pauses the iterator.
        If called with a True/False boolean, it sets the paused state to that value.
        This function is thread safe.

        :param bool val: the paused state to set (default: True)
        """
        asyncio.run_coroutine_threadsafe(self.async_pause(val), self.loop)

    def resume(self):
        """Resumes from a paused state.

        This function is thread safe."""
        self.pause(False)

    def stop(self):
        """Stops the iterator entirely causing the async for loop that caused it to complete.

        This function is thread safe."""
        self._stop = True
        self.resume()

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:

        if self._first_async_run:
            self.loop = asyncio.get_event_loop()
            await self._pb.async_verify_key()
            self._first_async_run = False

        async def _check_if_paused():
            await self._paused_lock.acquire()
            self._paused_lock.release()
            if self.stopped:
                raise StopAsyncIteration("PushbulletAsyncIterator has been told to stop.")

        try:
            await _check_if_paused()

            if self._limit and self._total_objects_returned >= self._limit:
                raise StopAsyncIteration("Already returned {} objects ({}) (limit = {})"
                                         .format(self._total_objects_returned, self._item_name, self._limit))

            # If empty, get some stuff
            empty_in_a_row = 0
            while self._get_more and not self._objects and self._pb._aio_session:
                await _check_if_paused()
                try:

                    # Do I/O
                    msg = await self._pb._async_get_data(self._url, params=self._params)

                except InvalidKeyError as ike:
                    raise ike  # Pass this one along

                except PushbulletError as pe:
                    self.log.debug("An error aborted the network request for _objects_asynciter: {}".format(pe))
                    # raise StopAsyncIteration(pe).with_traceback(sys.exc_info()[2])
                    raise pe

                else:
                    items_this_round = msg.get(self._item_name, [])
                    self.log.debug("Retrieved {} objects ({}).".format(len(items_this_round), self._item_name))
                    self._objects += items_this_round

                    if items_this_round:
                        empty_in_a_row = 0
                    else:
                        empty_in_a_row += 1
                        err_msg = "Received empty data ({}) from pushbullet {} times.".format(self._item_name,
                                                                                              empty_in_a_row)
                        self.log.debug(err_msg)
                        await asyncio.sleep(0.25 * empty_in_a_row)  # Just a little bit of throttling
                        if empty_in_a_row >= 3:
                            self._get_more = False
                            raise StopAsyncIteration(err_msg)

                    if "cursor" in msg:
                        self._params["cursor"] = msg.get("cursor")
                    else:
                        self._get_more = False

                # print("ARBITRARY DELAY FOR DEBUGGING")
                # await asyncio.sleep(1)

            if not self._objects:
                raise StopAsyncIteration("No more objects ({}) available from pushbullet.com."
                                         .format(self._item_name))

            # Prepare item to return
            await _check_if_paused()
            item = self._objects.pop(0)
            self._total_objects_returned += 1
            if self._post_process:
                if asyncio.iscoroutinefunction(self._post_process):
                    return await self._post_process(item)
                else:
                    return self._post_process(item)
            else:
                return item

        except StopAsyncIteration as sai:
            self.log.debug("Reason for iterator stopping: {}".format(sai))
            self._stop = sai
            raise sai


class AsyncPushbullet(Pushbullet):
    """Provides access to pushbullet.com services using asyncio."""

    # This is weird.  See the note in PushbulletAsyncIterator.
    _iterator_locks = []  # type: List[asyncio.Lock]

    def __init__(self, api_key: str = None, verify_ssl: bool = None, *kargs, **kwargs):
        Pushbullet.__init__(self, api_key, *kargs, **kwargs)

        self.loop = None  # type: asyncio.BaseEventLoop
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
            self.log.debug("Creating aiohttp-based, asyncio session.")

            self.loop = asyncio.get_event_loop()

            # print("Session is None, creating new one")
            headers = {"Access-Token": self.api_key}

            aio_connector = None  # type: aiohttp.TCPConnector
            if self.verify_ssl is not None and self.verify_ssl is False:
                self.log.info("SSL/TLS verification disabled")
                aio_connector = aiohttp.TCPConnector(verify_ssl=False)

            session = aiohttp.ClientSession(headers=headers, connector=aio_connector)
            self.log.debug("Created new session: {}".format(session))
            self._aio_session = session

            try:
                # raise Exception("Foo!")
                # This will recursively call aio_session() but that's OK
                # because self._aio_session caches it until we determine
                # if the key is valid in the line below.
                # Other purpose: Establish a timestamp for the most recent push
                _ = await self.async_get_pushes(limit=1,
                                                page_size=1,
                                                active_only=False)  # May throw invalid key error here

            except Exception as ex:
                await session.close()
                self._aio_session = None
                raise ex
                # if isinstance(ex, PushbulletError):
                #     raise ex
                # else:
                #     tb = sys.exc_info()[2]
                #     raise PushbulletError(ex).with_traceback(tb) from ex

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

        # try:
            async with aiohttp_func(url + "", proxy=self.proxy, **kwargs) as resp:  # Do HTTP
                code = resp.status
                msg = None
                # noinspection PyBroadException
                try:
                    if code != 204:  # 204 would be "No content"
                        msg = await resp.json()
                except:
                    pass
                finally:
                    if msg is None:
                        msg = await resp.read()

                return self._interpret_response(code, resp.headers, msg)

        # except Exception as ex:
        #     if isinstance(ex, PushbulletError):
        #         raise ex
        #     else:
        #         raise PushbulletError(ex).with_traceback(sys.exc_info()[2]) from ex

    async def _async_get_data(self, url: str, **kwargs) -> dict:
        session = await self.aio_session()
        msg = await self._async_http(session.get, url, **kwargs)
        return msg

    def _objects_asynciter(self, url, item_name,
                           limit: int = None,
                           page_size: int = None,
                           active_only: bool = True,
                           modified_after: float = None,
                           post_process: Callable = None) -> PushbulletAsyncIterator:
        """Returns an async iterator that retrieves objects from pushbullet.

        The iterator can be paused and restarted using the pause/resume functions.

        This required abandoning Python v3.5 in favor of v3.6+.
        """
        return PushbulletAsyncIterator(self, url, item_name, _limit=limit, _page_size=page_size,
                                       _active_only=active_only, _modified_after=modified_after,
                                       _post_process=post_process)

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

    def devices_asynciter(self,
                          limit: int = None,
                          page_size: int = None,
                          active_only: bool = None,
                          modified_after: float = None) -> PushbulletAsyncIterator[Device]:
        """Returns an interator that retrieves devices.

        The iterator can be paused with its pause/resume functions.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: PushbulletAsyncIterator[Device]
        """
        url = self.DEVICES_URL
        item_name = "devices"
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        return self._objects_asynciter(url, item_name, limit=limit, page_size=page_size,
                                       active_only=active_only, modified_after=modified_after,
                                       post_process=lambda x: Device(self, x))

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
            # List comprehension with async for requires Python 3.6+
            items = [x async for x in self.devices_asynciter(limit=None, active_only=True)]
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
                return next((z for z in self._devices if getattr(z, "nickname") == nickname), None)
            elif iden:
                return next((y for y in self._devices if y.iden == iden), None)

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
        xfer["msg"] = await self._async_post_data("{}/{}".format(self.DEVICES_URL, device.iden), data=data)
        return next(gen)

    async def async_remove_device(self, device: Device) -> dict:
        data = await self._async_delete_data("{}/{}".format(self.DEVICES_URL, device.iden))
        return data

    # ################
    # Chat
    #

    def chats_asynciter(self,
                        limit: int = None,
                        page_size: int = None,
                        active_only: bool = None,
                        modified_after: float = None) -> PushbulletAsyncIterator[Chat]:
        """Returns an interator that retrieves chats.

        The iterator can be paused with its pause/resume functions.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: PushbulletAsyncIterator[Chat]
        """
        url = self.CHATS_URL
        item_name = "chats"
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        return self._objects_asynciter(url, item_name, limit=limit, page_size=page_size,
                                       active_only=active_only, modified_after=modified_after,
                                       post_process=lambda x: Chat(self, x))

    async def async_get_chats(self, flush_cache: bool = False) -> List[Chat]:
        """Returns a list of Chat objects known by Pushbullet.

        This returns immediately with a cached copy, if available.
        If not available, or if flush_cache=True, then a call will be made to
        Pushbullet.com to retrieve a fresh list.

        :param bool flush_cache: whether or not to flush the cache first
        :return: list of Chat objects
        :rtype: List[Chat]
        """
        items = self._chats
        if items is None or flush_cache:
            items = [x async for x in self.chats_asynciter(limit=None, active_only=True)]
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
            return next((z for z in self._chats if getattr(z, "email") == email), None)

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

    def channels_asynciter(self,
                           limit: int = None,
                           page_size: int = None,
                           active_only: bool = None,
                           modified_after: float = None) -> PushbulletAsyncIterator[Channel]:
        """Returns an interator that retrieves channels.

        The iterator can be paused with its pause/resume functions.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: PushbulletAsyncIterator[Channel]
        """
        url = self.CHANNELS_URL
        item_name = "channels"
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        return self._objects_asynciter(url, item_name, limit=limit, page_size=page_size,
                                       active_only=active_only, modified_after=modified_after,
                                       post_process=lambda x: Channel(self, x))

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
            items = [x async for x in self.channels_asynciter(limit=None, active_only=True)]
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

        :param str channel_tag: the tag of the channel to fine
        :return: the Channel that was found or None if not found
        :rtype: Channel
        """
        _ = await self.async_get_channels()  # If no cached copy, create one

        def _get():
            return next((z for z in self._channels if z.tag == channel_tag), None)

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

    def subscriptions_asynciter(self,
                                limit: int = None,
                                page_size: int = None,
                                active_only: bool = None,
                                modified_after: float = None) -> PushbulletAsyncIterator[Subscription]:
        """Returns an interator that retrieves subscriptions.

        The iterator can be paused with its pause/resume functions.

        :param limit: maximum number to return (Default: None, unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: 0.0, all)
        :return: async iterator
        :rtype: PushbulletAsyncIterator[Subscription]
        """
        url = self.SUBSCRIPTIONS_URL
        item_name = "subscriptions"
        active_only = True if active_only is None else active_only  # Default value
        modified_after = 0.0 if modified_after is None else modified_after  # Default value
        return self._objects_asynciter(url, item_name, limit=limit, page_size=page_size,
                                       active_only=active_only, modified_after=modified_after,
                                       post_process=lambda x: Subscription(self, x))

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
            items = [x async for x in self.subscriptions_asynciter(limit=None, active_only=True)]
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
            return next((z for z in self._subscriptions
                         if z.channel and z.channel.tag == channel_tag), None)

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

    def pushes_asynciter(self,
                         limit: int = None,
                         page_size: int = None,
                         active_only: bool = None,
                         modified_after: float = None,
                         dereference_device_iden: bool = True) -> PushbulletAsyncIterator[dict]:
        """Returns an interator that retrieves pushes.

        The iterator can be paused with its pause/resume functions.

        Set modified_after = 0.0 and active_only = False to retrieve the entire history.
        Careful! It may take a while!

        :param limit: maximum number to return (Default: unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: since last call)
        :return: async iterator
        :rtype: PushbulletAsyncIterator[dict]
        """
        url = self.PUSH_URL
        item_name = "pushes"
        active_only = True if active_only is None else active_only  # Default value
        modified_after = self.most_recent_timestamp if modified_after is None else modified_after  # Default value

        async def _post_process_push(push):
            # Bookkeeping: keep track of the most recent timestamp ever seen
            modified = push.get("modified", 0)
            if modified > self.most_recent_timestamp:
                self.most_recent_timestamp = modified

            # Add human-readable fields for date/time stamps
            for date_field in ("modified", "created"):
                if push.get(date_field):
                    date_cleartext = datetime.datetime.fromtimestamp(push.get(date_field)).strftime('%c')
                    push["{}:cleartext".format(date_field)] = date_cleartext

            # Derereference device iden?
            if dereference_device_iden:
                for field in ("source_device_iden", "target_device_iden"):
                    if field in push:
                        dev_iden = push.get(field)
                        dev = await self.async_get_device(iden=dev_iden)
                        if dev:
                            push["{}:nickname".format(field)] = dev.nickname

            return push

        return self._objects_asynciter(url, item_name, limit=limit, page_size=page_size,
                                       active_only=active_only, modified_after=modified_after,
                                       post_process=_post_process_push)

    async def async_get_pushes(self,
                               limit: int = None,
                               page_size: int = None,
                               active_only: bool = None,
                               modified_after: float = None,
                               dereference_device_iden: bool = True) -> List[dict]:

        """Returns a list of pushes.

        :param limit: maximum number to return (Default: unlimited)
        :param page_size: number to retrieve from each call to pushbullet.com
        :param active_only: retrieve only active items (Default: True)
        :param modified_after: retrieve only items modified after this timestamp (Default: since last call)
        :return: list of pushes
        :rtype: List[dict]
        """
        items = [x async for x in self.pushes_asynciter(limit=limit,
                                                        page_size=page_size,
                                                        active_only=active_only,
                                                        modified_after=modified_after,
                                                        dereference_device_iden=dereference_device_iden)]
        return items

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

    async def async_push_note(self, title: str = None,
                              body: str = None,
                              device: Device = None,
                              chat: Chat = None,
                              email: str = None,
                              channel: Channel = None) -> dict:
        data = {"type": "note"}#, "title": title, "body": body}
        if title:
            data["title"] = str(title)
        if body:
            data["body"] = str(body)
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
        _ = await self.async_get_user()  # cache user info
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

        :param str file_path: path to the file to upload
        :param str file_type: optional mime type of file to upload
        :param bool show_progress: show a progress bar on the terminal
        :return: data about what got uploaded
        :rtype: dict
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
