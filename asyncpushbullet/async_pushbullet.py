import asyncio
import hashlib
import os

import aiohttp
import io

from tqdm import tqdm

from asyncpushbullet import Device
from asyncpushbullet.channel import Channel
from asyncpushbullet.chat import Chat
from asyncpushbullet.tqio import tqio
from .pushbullet import Pushbullet, PushbulletError

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"


class AsyncPushbullet(Pushbullet):
    def __init__(self, api_key: str, verify_ssl: bool = None,
                 loop: asyncio.AbstractEventLoop = None, **kwargs):
        Pushbullet.__init__(self, api_key, **kwargs)
        self.loop = loop or asyncio.get_event_loop()

        # TODO: Proxies
        self._proxy = kwargs.get("proxy")  # type: dict

        self._aio_sessions = {}  # type: {asyncio.AbstractEventLoop:aiohttp.ClientSession}
        self.verify_ssl = verify_ssl

    async def async_verify_key(self):
        """
        Triggers a call to Pushbullet.com that will throw an
        InvalidKeyError if the key is not valid.
        """
        await self.aio_session()

    async def aio_session(self) -> aiohttp.ClientSession:

        # Sessions are created/handled on a per-loop basis
        loop = asyncio.get_event_loop()
        session = self._aio_sessions.get(loop)  # type: aiohttp.ClientSession

        if session is None:
            headers = {"Access-Token": self.api_key}

            aio_connector = None  # type: aiohttp.TCPConnector
            if self.verify_ssl is not None and self.verify_ssl is False:
                self.log.info("SSL/TLS verification disabled")
                aio_connector = aiohttp.TCPConnector(verify_ssl=False, loop=loop)

            # self.log.debug("Creating aiohttp session on loop {}".format(id(loop)))
            session = aiohttp.ClientSession(headers=headers, connector=aio_connector)  # , loop=loop)
            self.log.debug("Created aiohttp session {} on loop {}".format(id(session), id(loop)))
            self._aio_sessions[loop] = session  # Save session for this loop

            if self.most_recent_timestamp == 0:
                self.log.debug("Retrieving one push to set initial latest timestamp")
                await self.async_get_pushes(limit=1)  # May throw invalid key error here

            else:
                self.log.debug("Retrieved aiohttp session {} on loop {}".format(id(session), id(loop)))

        return session

    async def close(self):
        super().close()

        loop = asyncio.get_event_loop()
        if loop in self._aio_sessions:
            self._aio_sessions[loop].close()
            del self._aio_sessions[loop]

    def close_all(self):
        for loop in self._aio_sessions.keys():
            asyncio.run_coroutine_threadsafe(self.close(), loop=loop)

    # ################
    # IO Methods
    #

    async def _async_http(self, aiohttp_func, url: str, **kwargs) -> dict:

        async with aiohttp_func(url, proxy=self._proxy, **kwargs) as resp:  # Do HTTP

            code = resp.status
            msg = None
            try:
                if code != 204:  # No content
                    msg = await resp.json()
            except:
                pass
            finally:
                if msg is None:
                    msg = await resp.text()

            return self._interpret_response(code, resp.headers, msg)

    async def _async_get_data(self, url: str, **kwargs) -> dict:
        session = await self.aio_session()
        msg = await self._async_http(session.get, url, **kwargs)
        return msg

    async def _async_get_data_with_pagination(self, url: str, item_name: str, **kwargs) -> dict:
        gen = self._get_data_with_pagination_generator(url, item_name, **kwargs)
        xfer = next(gen)  # Prep params
        msg = {}
        while xfer.get("get_more", False):
            args = xfer.get("kwargs", {})  # type: dict
            xfer["msg"] = await self._async_get_data(url, **args)
            msg = next(gen)
        return msg

    async def _async_post_data(self, url: str, **kwargs) -> dict:
        session = await self.aio_session()
        msg = await self._async_http(session.post, url, **kwargs)
        return msg

    async def _async_delete_data(self, url: str, **kwargs) -> dict:
        session = await self.aio_session()
        msg = await self._async_http(session.delete, url, **kwargs)

        return msg

    async def _async_push(self, data: dict) -> dict:
        msg = await self._async_post_data(self.PUSH_URL, data=data)
        return msg

    # ################
    # Device
    #

    async def _async_load_devices(self):
        self._devices = []
        msg = await self._async_get_data_with_pagination(self.DEVICES_URL, "devices", params={"active": "true"})
        device_list = msg.get('devices', [])
        for device_info in device_list:
            if device_info.get("active"):
                d = Device(self, device_info)
                self._devices.append(d)
        self.log.info("Found {} active devices".format(len(self._devices)))

    async def async_get_device(self, nickname: str = None, iden: str = None) -> Device:
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
            await self._async_load_devices()  # Refresh cache once
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

    async def _async_load_chats(self):
        self._chats = []
        msg = await self._async_get_data_with_pagination(self.CHATS_URL, "chats", params={"active": "true"})
        chat_list = msg.get('chats', [])
        for chat_info in chat_list:
            if chat_info.get("active"):
                c = Chat(self, chat_info)
                self.chats.append(c)
        self.log.info("Found {} active chats".format(len(self._chats)))

    async def async_get_chat(self, email: str) -> Chat:

        if self._chats is None:
            self._chats = []

        def _get():
            return next((x for x in self._chats if x.email == email), None)

        x = _get()
        if x is None:
            self.log.debug("Chat {} not found in cache.  Refreshing.".format(email))
            await self._async_load_chats()  # Refresh cache once
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

    async def _async_load_channels(self):
        self._channels = []
        msg = await self._async_get_data_with_pagination(self.CHANNELS_URL, "channels", params={"active": "true"})
        channel_list = msg.get('channels', [])
        for channel_info in channel_list:
            if channel_info.get("active"):
                c = Channel(self, channel_info)
                self.channels.append(c)
        self.log.info("Found {} active channels".format(len(self._channels)))

    async def async_get_channel(self, channel_tag: str) -> Channel:
        if self._channels is None:
            self._channels = []

        def _get():
            return next((x for x in self._channels if x.channel_tag == channel_tag), None)

        x = _get()
        if x is None:
            self.log.debug("Channel {} not found in cache.  Refreshing.".format(channel_tag))
            await self._async_load_channels()  # Refresh cache once
            x = _get()
        return x

    # ################
    # Pushes
    #

    async def async_get_pushes(self, modified_after: float = None, limit: int = None,
                               filter_inactive: bool = True) -> [dict]:
        gen = self._get_pushes_generator(modified_after=modified_after,
                                         limit=limit, filter_inactive=filter_inactive)
        xfer = next(gen)  # Prep http params
        data = xfer.get('data', {})
        xfer["msg"] = await self._async_get_data_with_pagination(self.PUSH_URL, "pushes", params=data)
        return next(gen)  # Post process response

    async def async_get_new_pushes(self, limit: int = None,
                                   filter_inactive: bool = True) -> [dict]:
        pushes = await self.async_get_pushes(modified_after=self.most_recent_timestamp,
                                             limit=limit, filter_inactive=filter_inactive)
        return pushes

    async def async_dismiss_push(self, iden: str) -> dict:
        if type(iden) is dict and "iden" in iden:
            iden = iden["iden"]  # In case user passes entire push
        data = {"dismissed": "true"}
        msg = await self._async_post_data("{}/{}".format(self.PUSH_URL, iden), data=data)
        return msg

    async def async_delete_push(self, iden: str) -> dict:
        if type(iden) is dict and "iden" in iden:
            iden = iden["iden"]  # In case user passes entire push
        msg = await self._async_delete_data("{}/{}".format(self.PUSH_URL, iden))
        return msg

    async def async_delete_pushes(self) -> dict:
        msg = await self._async_delete_data(self.PUSH_URL)
        return msg

    async def async_push_note(self, title: str, body: str, device: Device = None,
                              chat: Chat = None, email: str = None, channel: Channel = None) -> dict:
        data = {"type": "note", "title": title, "body": body}
        data.update(Pushbullet._recipient(device, chat, email, channel))
        msg = await self._async_push(data)
        return msg

    async def async_push_link(self, title: str, url: str, body: str = None,
                              device: Device = None, chat: Chat = None, email: str = None,
                              channel: Channel = None) -> dict:
        data = {"type": "link", "title": title, "url": url, "body": body}
        data.update(Pushbullet._recipient(device, chat, email, channel))
        msg = await self._async_push(data)
        return msg

    async def async_push_sms(self, device: Device, number: str, message: str) -> dict:
        gen = self._push_sms_generator(device, number, message)
        xfer = next(gen)  # Prep params
        data = xfer.get("data")
        xfer["msg"] = await self._async_post_data(self.EPHEMERALS_URL, data=data)
        return next(gen)  # Post process

    # ################
    # Files
    #

    async def async_upload_file(self, file_path: str, file_type: str = None,
                                suppress_progress: bool = False) -> dict:
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

        file_name = xfer["data"]["file_name"]
        file_type = xfer["data"]["file_type"]

        # data = aiohttp.FormData()
        # data.add_field('file',
        #                # tqio(open(args.file, "rb")),
        #                tqio(args.file),
        #                # stream,
        #                filename=file_name,
        #                content_type=file_type)

        if suppress_progress:
            with open(file_path, "rb") as f:
                xfer["msg"] = await self._async_post_data(xfer["upload_url"], data={"file": f})
        else:
            with tqio(file_path) as f:
                xfer["msg"] = await self._async_post_data(xfer["upload_url"], data={"file": f})

        return next(gen)  # Prep response

    async def async_push_file(self, file_name: str, file_url: str, file_type: str,
                              body: str = None, title: str = None, device: Device = None,
                              chat: Chat = None, email: str = None,
                              channel: Channel = None) -> dict:
        gen = self._push_file_generator(file_name, file_url, file_type, body=body, title=title,
                                        device=device, chat=chat, email=email, channel=channel)
        xfer = next(gen)
        data = xfer.get("data")
        xfer["msg"] = await self._async_push(data)
        return next(gen)

