#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import pprint
import sys

import lorem

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import Pushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
    pb = Pushbullet(API_KEY, proxy=PROXY)

    title = "Greetings"
    body = "Welcome to accessing Pushbullet with Python"
    body = lorem.sentence()
    resp = pb.push_note(title, body)
    print("Response", pprint.pformat(resp))


if __name__ == "__main__":
    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()
    main()
