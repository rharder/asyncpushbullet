#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A simple example showing how to mirror notifications.

This example has not been verified with the asyncio-based code.
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import time

from asyncpushbullet import Pushbullet
from asyncpushbullet.listener import Listener


class Mirrorer:

    def __init__(self, auth_key, temp_folder, device_name, last_push=time.time(), device_iden=None):
        self.temp_folder = temp_folder
        if not os.path.exists(self.temp_folder):
            os.makedirs(temp_folder)

        self._auth_key = auth_key
        self.pb = Pushbullet(self._auth_key)
        self.listener = Listener(self.pb, self.watcher)

        self.last_push = last_push

        self.device = None
        if device_iden:
            devices = self.pb.get_devices()
            results = [d for d in devices if d.iden == device_iden and d.active]
            self.device = results[0] if results else None

        if not self.device:
            try:
                device = self.pb.new_device(device_name)
                print("Created new device:", device_name, "iden:", device.iden)
                self.device = device
            except:
                print("Error: Unable to create device")
                raise

        self.check_pushes()

    def save_icon(self, b64_asset):
        hash = hashlib.md5(b64_asset.encode()).hexdigest()
        path = os.path.join(self.temp_folder, hash)
        if os.path.exists(path):
            return path
        else:
            decoded = base64.b64decode(b64_asset)
            with open(path, "wb") as image:
                image.write(decoded)
            return path

    def check_pushes(self):
        pushes = self.pb.get_pushes(self.last_push)
        for push in pushes:
            if not isinstance(push, dict):
                # not a push object
                continue
            if ((push.get("target_device_iden", self.device.iden) == self.device.iden) and not (
            push.get("dismissed", True))):
                self.notify(push.get("title", ""), push.get("body", ""))
                self.pb.dismiss_push(push.get("iden"))
            self.last_push = max(self.last_push, push.get("created"))

    def watcher(self, push):
        if push["type"] == "push" and push["push"]["type"] == "mirror":
            print("MIRROR")
            image_path = self.save_icon(push["push"]["icon"])
            self.notify(push["push"]["title"],
                        push["push"]["body"], image_path)
        elif push["type"] == "tickle":
            print("TICKLE")
            self.check_pushes()

    def notify(self, title, body, image=None):
        subprocess.Popen(["notify-send", title, body, "-i", image or ""])
        print(title)
        print(body)

    def dump_config(self, path):
        config = {"temp_folder": self.temp_folder,
                  "auth_key": self._auth_key,
                  "device_name": self.device.nickname,
                  "device_iden": self.device.iden}
        with open(path, "w") as conf:
            json.dump(config, conf)

    def run(self):
        try:
            self.listener.run_forever()
        except KeyboardInterrupt:
            self.listener.close()


def main():
    config_file = sys.argv[1]
    with open(config_file) as conf:
        config = json.load(conf)

    m = Mirrorer(**config)
    m.run()
    m.dump_config(config_file)


if __name__ == '__main__':
    main()
