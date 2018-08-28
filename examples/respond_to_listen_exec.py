#!/usr/bin/env python3
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
from asyncpushbullet import Pushbullet

__encoding__ = "utf-8"
API_KEY = ""  # YOUR API KEY


def main():
    with io.open(sys.stdin.fileno(), mode="r", encoding="utf-8") as f:
        stdin = f.read()
    try:
        recvd_push = json.loads(stdin)
    except json.decoder.JSONDecodeError as e:
        # print(e, file=sys.stderr)
        raise e
    else:

        if recvd_push.get("body", "").lower().strip() == "imagesnap":
            # Take a picture and upload
            # Simulate it for now

            try:
                # Temp file to house the image file
                f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                f.close()

                # PRETEND TO TAKE A PICTURE
                # fakepic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.jpg")
                # shutil.copy(fakepic, f.name)

                # Take a picture
                proc = subprocess.run(["imagesnap", f.name],
                                      # proc = subprocess.run(["notepad.exe", f.name],
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,
                                      timeout=10,
                                      encoding=__encoding__)

                # Upload picture
                proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
                pb = Pushbullet(API_KEY, proxy=proxy)
                resp = pb.upload_file(f.name)
                file_type = resp.get("file_type")
                file_url = resp.get("file_url")
                file_name = resp.get("file_name")

                # Provide a response via stdout
                myresp = {
                    "type": "file",
                    "title": "Imagesnap",
                    "body": "{}\n{}".format(proc.stdout, proc.stderr).strip(),
                    "file_name": file_name,
                    "file_type": file_type,
                    "file_url": file_url
                }
                print(json.dumps(myresp))

            finally:

                os.remove(f.name)


if __name__ == "__main__":

    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    main()
