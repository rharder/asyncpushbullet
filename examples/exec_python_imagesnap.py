#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Experimental script that responds to a ListenApp exec command.
"""
import json
import os
import subprocess
import sys
import tempfile

# sys.path.append("..")  # Since examples are buried one level into source tree
from asyncpushbullet import AsyncPushbullet

ENCODING = "utf-8"
# API_KEY = ""  # YOUR API KEY
# PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")

# COUNT=0

async def on_push(recvd_push: dict, pb: AsyncPushbullet):
    raise Exception("foo!", __name__)
    # global COUNT
    # COUNT += 1
    # print("RECEIVED SO FAR:", COUNT)
    # print("CALLED ME!")
    if recvd_push.get("body", "").lower().strip() == "imagesnap":

        # Temp file to house the image file
        temp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_img.close()


        try:

            # Take a picture and upload
            # PRETEND TO TAKE A PICTURE
            # import shutil
            # fakepic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.jpg")
            # shutil.copy(fakepic, temp_img.name)

            # Take a picture
            proc = subprocess.run(["imagesnap", temp_img.name],
            # proc = subprocess.run(["clip.exe"],  # Debugging
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  timeout=10,
                                  encoding=ENCODING)

            # Upload picture
            resp = await pb.async_upload_file_to_transfer_sh(temp_img.name)
            file_type = resp.get("file_type")
            file_url = resp.get("file_url")
            file_name = resp.get("file_name")

            # Provide a response
            stdout_txt = proc.stdout
            stderr_txt = proc.stderr
            # myresp = {
            #     "type": "file",
            #     "title": "Imagesnap",
            #     "body": "{}\n{}".format(stdout_txt, stderr_txt).strip(),
            #     "file_name": file_name,
            #     "file_type": file_type,
            #     "file_url": file_url,
            #     "received_push": recvd_push
            # }

            dev_iden = recvd_push.get("source_device_iden")
            dev = await pb.async_get_device(iden=dev_iden)
            await pb.async_push_file(file_name=file_name, file_url=file_url, file_type=file_type,
                                     title="Imagesnap", body="{}\n{}".format(stdout_txt, stderr_txt).strip(),
                                     device=dev)

        except Exception as e:
            raise e
            # print("Error:", e, file=sys.stderr)

        finally:
            os.remove(temp_img.name)
