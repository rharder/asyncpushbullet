import asyncio
import os
from pprint import pprint

import aiohttp
import datetime

from .device import Device
from .errors import PushbulletError, InvalidKeyError
from .pushbullet import Pushbullet, get_file_type
from .filetype import _guess_file_type
from .chat import Chat


class AioPushbullet(Pushbullet):
    def __init__(self, api_key, **kwargs):
        Pushbullet.__init__(self, api_key, **kwargs)

        self._proxy = kwargs.get("proxy")  # type: dict
        self._aio_session = None  # type: aiohttp.ClientSession

        asyncio.ensure_future(self.__aio__init__())  # Coroutine __init__

    async def __aio__init__(self):
        headers = {"Access-Token": self.api_key}
        self._aio_session = aiohttp.ClientSession(headers=headers)

    # ################
    # IO Methods
    #

    async def _async_http(self, func, url, **kwargs):

        async with func(url, proxy=self._proxy, **kwargs) as resp:  # Do HTTP

            code = resp.status
            msg = None
            try:
                msg = await resp.json()
            except:
                pass
            finally:
                if msg is None:
                    msg = resp.text  # TODO: IS THIS THE RIGHT WAY TO GET TEXT

            return self._interpret_response(code, resp.headers, msg)

    async def _async_get_data(self, url, **kwargs):
        msg = await self._async_http(self._aio_session.get, url, **kwargs)
        return msg

    async def _async_post_data(self, url, **kwargs):
        msg = await self._async_http(self._aio_session.post, url, **kwargs)
        return msg

    async def _async_delete_data(self, url, **kwargs):
        msg = await self._async_http(self._aio_session.delete, url, **kwargs)
        return msg

    async def _async_push(self, data):
        msg = await self._async_post_data(self.PUSH_URL, data=data)
        return msg

    # ################
    # Device
    #

    async def async_new_device(self, nickname, manufacturer=None, model=None, icon="system", func=None):
        gen = self._new_device(nickname, manufacturer=manufacturer, model=model, icon=icon)
        xfer = next(gen)  # Prep http params
        data = xfer["data"]
        xfer["msg"] = await self._async_post_data(self.DEVICES_URL, data=data)
        return next(gen)  # Post process response

    async def async_edit_device(self, device, nickname=None, model=None, manufacturer=None, icon=None, has_sms=None):
        gen = self._edit_device(device, nickname=nickname, model=model,
                                manufacturer=manufacturer, icon=icon, has_sms=has_sms)
        xfer = next(gen)
        data = xfer["data"]
        xfer["msg"] = await self._async_post_data("{}/{}".format(self.DEVICES_URL, device.device_iden), data=data)
        return next(gen)

    async def async_remove_device(self, device):
        data = await self._async_delete_data("{}/{}".format(self.DEVICES_URL, device.device_iden))
        return data

    # ################
    # Chat
    #

    async def async_new_chat(self, email):
        gen = self._new_chat(email)
        xfer = next(gen)
        xfer["msg"] = await self._async_post_data(self.CHATS_URL, data=xfer.get("data", {}))
        return next(gen)

    async def async_edit_chat(self, chat, muted=False):
        gen = self._edit_chat(chat, muted)
        xfer = next(gen)
        data = xfer.get('data', {})
        xfer["msg"] = await self._async_post_data("{}/{}".format(self.CHATS_URL, chat.iden), data=data)
        return next(gen)

    async def async_remove_chat(self, chat):
        msg = await self._async_delete_data("{}/{}".format(self.CHATS_URL, chat.iden))
        return msg

    # ################
    # Pushes
    #

    async def async_get_pushes(self, modified_after=None, limit=None, filter_inactive=True):
        gen = self._get_pushes(modified_after=modified_after,
                               limit=limit, filter_inactive=filter_inactive)
        xfer = next(gen)
        resp = []
        while xfer["get_more_pushes"]:
            xfer["msg"] = await self._async_get_data(self.PUSH_URL, params=xfer.get('data', {}))
            resp = next(gen)
        return resp

    async def async_get_new_pushes(self, limit=None, filter_inactive=True):
        pushes = await self.async_get_pushes(modified_after=self._most_recent_timestamp,
                                           limit=limit, filter_inactive=filter_inactive)
        return pushes

    async def async_dismiss_push(self, iden):
        data = {"dismissed": True}
        msg = await self._async_post_data("{}/{}".format(self.PUSH_URL, iden), data=data)
        return msg

    async def async_delete_push(self, iden):
        msg = await self._async_delete_data("{}/{}".format(self.PUSH_URL, iden))
        return msg

    async def async_delete_pushes(self):
        msg = await self._async_delete_data(self.PUSH_URL)
        return msg

    async def async_upload_file(self, file_path, file_type=None):
        gen = self._upload_file(file_path, file_type=file_type)

        xfer = next(gen)  # Prep request params

        data = xfer["data"]
        xfer["msg"] = await self._async_post_data(self.UPLOAD_REQUEST_URL, data=data)

        next(gen)  # Prep upload params

        data = xfer["data"]
        with open(file_path, "rb") as f:
            xfer["msg"] = await self._async_post_data(xfer["upload_url"], data={"file": f})

        return next(gen)  # Prep response


    # async def aio_upload_file(self, file_path, file_type=None):
    #     file_name = os.path.basename(file_path)
    #     if not file_type:
    #         with open(file_path, "rb") as f:
    #             file_type = get_file_type(f, file_name)
    #
    #     data = {"file_name": file_name, "file_type": file_type}
    #
    #     # Request url for file upload
    #     msg = await self._async_post_data(self.UPLOAD_REQUEST_URL, data=data)
    #
    #     upload_url = msg.get("upload_url")  # Where to upload
    #     file_url = msg.get("file_url")  # Resulting destination
    #
    #     # Upload the file
    #     with open(file_path, "rb") as f:
    #         msg = await self._async_post_data(upload_url, data={'file': f})
    #
    #     return {"file_type": file_type, "file_url": file_url, "file_name": file_name, "resp": msg}



    async def async_push_file(self, file_name, file_url, file_type, body=None, title=None, device=None, chat=None, email=None,
                  channel=None):
        gen = self._push_file(file_name, file_url, file_type, body=body, title=title,
                              device=device, chat=chat, email=email, channel=channel)
        xfer = next(gen)
        data = xfer.get("data")
        xfer["msg"] = await self._async_push(data)
        return next(gen)

    async def aio_push_file(self, file_name, file_url,
                            file_type=None, body=None, title=None, device=None,
                            chat=None, email=None, channel=None):
        if file_type is None:
            file_type = _guess_file_type(file_name)
        data = {"type": "file", "file_type": file_type, "file_url": file_url, "file_name": file_name}
        if body:
            data["body"] = body
        if title:
            data["title"] = title
        data.update(Pushbullet._recipient(device, chat, email, channel))
        msg = await self._async_push(data)
        return msg

    async def push_note(self, title, body, device=None, chat=None, email=None, channel=None):
        data = {"type": "note", "title": title, "body": body}
        data.update(Pushbullet._recipient(device, chat, email, channel))
        msg = await self._async_push(data)
        return msg

    async def aio_push_link(self, title, url, body=None, device=None, chat=None, email=None, channel=None):
        data = {"type": "link", "title": title, "url": url, "body": body}
        data.update(Pushbullet._recipient(device, chat, email, channel))
        msg = await self._async_push(data)
        return msg

    async def aio_push_sms(self, device, number, message):
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
                "encrypted": True
            }

        msg = await self._async_post_data(self.EPHEMERALS_URL, data=data)
        return msg

    async def async_get_me(self):
        msg = await self._async_get_data(Pushbullet.ME_URL)
        return msg

        #
