#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Experimental script that responds to a ListenApp exec command.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import Pushbullet, AsyncPushbullet

ENCODING = "utf-8"
API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
    with io.open(sys.stdin.fileno(), mode="r", encoding="utf-8") as f:
        stdin = f.readlines()
    del f

    title = stdin[0].strip()
    body = "\n".join(stdin[1:])

    print("Title was: {}".format(title))
    print("Body was: {}".format(body))


if __name__ == "__main__":

    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    main()
