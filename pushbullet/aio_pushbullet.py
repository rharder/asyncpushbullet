import asyncio
import os
from pprint import pprint

import aiohttp

from .device import Device
from .errors import PushbulletError, InvalidKeyError
from .pushbullet import Pushbullet, get_file_type
from .filetype import _guess_file_type
from .chat import Chat


class AioPushbullet(Pushbullet):
    def __init__(self, api_key, **kwargs):
        Pushbullet.__init__(self, api_key, **kwargs)
        self._proxy = kwargs.get("proxy")
        self._aio_session = None  # type: aiohttp.ClientSession

        asyncio.ensure_future(self.__aio__init__())

    @asyncio.coroutine
    def __aio__init__(self):
        headers = {"Access-Token": self.api_key}
        self._aio_session = aiohttp.ClientSession(headers=headers)

    @asyncio.coroutine
    def aio_get_meZZZ(self):
        resp = yield from self._aio_session.get(Pushbullet.ME_URL, proxy=self._proxy)
        try:
            me = yield from resp.json()
            return me
        finally:
            yield from resp.release()

    @asyncio.coroutine
    def aio_get_me(self):
        msg = yield from self._aio_get_data(Pushbullet.ME_URL)
        return msg

    @asyncio.coroutine
    def _aio_http(self, func, url, **kwargs):
        resp = yield from func(url, proxy=self._proxy, **kwargs)
        try:
            if resp.status in (401, 403):
                raise InvalidKeyError()
            elif resp.status == 429:
                raise PushbulletError("Too Many Requests, you have been ratelimited")
            elif resp.status == 204:  # No response
                msg = {}
            elif resp.status != 200:
                msg = yield from resp.json()
                raise PushbulletError(resp.status, msg)
            else:
                msg = yield from resp.json()

            return msg
        finally:
            yield from resp.release()

    @asyncio.coroutine
    def _aio_get_data(self, url, **kwargs):
        resp = yield from self._aio_http(self._aio_session.get, url, **kwargs)
        return resp

    @asyncio.coroutine
    def _aio_post_data(self, url, **kwargs):
        resp = yield from self._aio_http(self._aio_session.post, url, **kwargs)
        return resp

    @asyncio.coroutine
    def _aio_delete_data(self, url, **kwargs):
        resp = yield from self._aio_http(self._aio_session.delete, url, **kwargs)
        return resp


    @asyncio.coroutine
    def _aio_push(self, data):
        msg = self._aio_post_data(self.PUSH_URL, data=data)
        return msg

    @asyncio.coroutine
    def aio_new_device(self, nickname, manufacturer=None, model=None, icon="system"):
        data = {"nickname": nickname, "icon": icon}
        data.update({k: v for k, v in
                     (("model", model), ("manufacturer", manufacturer)) if v is not None})
        data = yield from self._aio_post_data(self.DEVICES_URL, data=data)
        if data:
            new_device = Device(self, data)
            self.devices.append(new_device)
            return new_device
        else:
            raise PushbulletError("No data received from post to " + self.DEVICES_URL)

    @asyncio.coroutine
    def aio_remove_device(self, device):
        iden = device.device_iden
        data = yield from self._aio_delete_data("{}/{}".format(self.DEVICES_URL, iden))
        return data

    @asyncio.coroutine
    def aio_edit_device(self, device, nickname=None, model=None, manufacturer=None, icon=None):
        data = {k: v for k, v in
                (("nickname", nickname or device.nickname), ("model", model),
                 ("manufacturer", manufacturer), ("icon", icon)) if v is not None}
        iden = device.device_iden
        msg = yield from self._aio_post_data("{}/{}".format(self.DEVICES_URL, iden), data=data)
        print("msg", msg)
        new_device = Device(self, msg)
        self.devices[self.devices.index(device)] = new_device
        return new_device

    @asyncio.coroutine
    def aio_get_pushes(self, modified_after=0, limit=None, filter_inactive=True):
        data = {"modified_after": modified_after, "limit": limit}
        if filter_inactive:
            data['active'] = "true"

        pushes_list = []
        get_more_pushes = True
        while get_more_pushes:
            msg = yield from self._aio_get_data(self.PUSH_URL, params=data)

            pushes_list += msg.get('pushes', [])
            if 'cursor' in msg and (not limit or len(pushes_list) < limit):
                data['cursor'] = msg['cursor']
            else:
                get_more_pushes = False

        if len(pushes_list) > 0 and pushes_list[0].get('modified', 0) > self._most_recent_timestamp:
            self._most_recent_timestamp = pushes_list[0]['modified']

        return pushes_list

    @asyncio.coroutine
    def get_new_pushes(self, limit=None, filter_inactive=True):
        pushes = yield from self.aio_get_pushes(modified_after=self._most_recent_timestamp,
                                                limit=limit, filter_inactive=filter_inactive)
        return pushes

    @asyncio.coroutine
    def aio_dismiss_push(self, iden):
        data = {"dismissed": True}
        # r = self._session.post("{}/{}".format(self.PUSH_URL, iden), data=json.dumps(data))
        msg = yield from self._aio_post_data("{}/{}".format(self.PUSH_URL, iden), data=data)
        return msg

    @asyncio.coroutine
    def aio_delete_push(self, iden):
        msg = yield from self._aio_delete_data("{}/{}".format(self.PUSH_URL, iden))
        return msg

    @asyncio.coroutine
    def aio_delete_pushes(self):
        msg = yield from self._aio_delete_data(self.PUSH_URL)
        return msg

    @asyncio.coroutine
    def aio_new_chat(self, email):
        data = {"email": email}
        msg = yield from self._aio_post_data(self.CHATS_URL, data=data)
        new_chat = Chat(self, msg)
        self.chats.append(new_chat)
        return new_chat

    @asyncio.coroutine
    def aio_edit_chat(self, chat, muted=False):
        data = {"muted": str(muted).lower()}
        iden = chat.iden
        msg = yield from self._aio_post_data("{}/{}".format(self.CHATS_URL, iden), data=data)
        pprint(msg)
        new_chat = Chat(self, msg)
        self.chats[self.chats.index(chat)] = new_chat
        return new_chat

    @asyncio.coroutine
    def aio_remove_chat(self, chat):
        iden = chat.iden
        msg = yield from self._aio_delete_data("{}/{}".format(self.CHATS_URL, iden))
        self.chats.remove(chat)
        return msg

    @asyncio.coroutine
    def aio_upload_file(self, file_path, file_type=None):
        file_name = os.path.basename(file_path)
        if not file_type:
            with open(file_path, "rb") as f:
                file_type = get_file_type(f, file_name)

        data = {"file_name": file_name, "file_type": file_type}

        # Request url for file upload
        msg = yield from self._aio_post_data(self.UPLOAD_REQUEST_URL, data=data)

        upload_url = msg.get("upload_url")  # Where to upload
        file_url = msg.get("file_url")  # Resulting destination

        # Upload the file
        with open(file_path, "rb") as f:
            msg = yield from self._aio_post_data(upload_url, data={'file':f})

        return {"file_type": file_type, "file_url": file_url, "file_name": file_path, "resp": msg}

    @asyncio.coroutine
    def aio_push_file(self, file_name, file_url, file_type=None, body=None, title=None, device=None, chat=None, email=None,
                  channel=None):
        if file_type is None:
            file_type = _guess_file_type(file_name)

        data = {"type": "file", "file_type": file_type, "file_url": file_url, "file_name": file_name}
        if body:
            data["body"] = body

        if title:
            data["title"] = title

        data.update(Pushbullet._recipient(device, chat, email, channel))

        msg = yield from self._aio_push(data)
        return msg

    @asyncio.coroutine
    def push_note(self, title, body, device=None, chat=None, email=None, channel=None):
        data = {"type": "note", "title": title, "body": body}
        data.update(Pushbullet._recipient(device, chat, email, channel))
        msg = yield from self._aio_push(data)
        return msg


    @asyncio.coroutine
    def aio_push_link(self, title, url, body=None, device=None, chat=None, email=None, channel=None):
        data = {"type": "link", "title": title, "url": url, "body": body}
        data.update(Pushbullet._recipient(device, chat, email, channel))
        msg = yield from self._aio_push(data)
        return msg


    @asyncio.coroutine
    def aio_push_sms(self, device, number, message):
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

        msg = self._aio_post_data(self.EPHEMERALS_URL, data=data)
        return msg


