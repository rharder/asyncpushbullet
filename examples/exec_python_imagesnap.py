#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Experimental script that responds to a ListenApp exec command.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile

# sys.path.append("..")  # Since examples are buried one level into source tree
import traceback

from asyncpushbullet import AsyncPushbullet

ENCODING = "utf-8"


async def on_push(recvd_push: dict, pb: AsyncPushbullet):

    # await asyncio.sleep(99)
    if recvd_push.get("body", "").lower().strip() == "imagesnap":

        # Temp file to house the image file
        temp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_img.close()

        try:
            # Take a picture and upload
            # PRETEND TO TAKE A PICTURE DURING DEBUGGING
            # import shutil
            # fakepic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.jpg")
            # shutil.copy(fakepic, temp_img.name)

            stdout_txt = None  # type: str
            stderr_txt = None  # type: str

            cmd_path = "imagesnap"
            # cmd_path = "mate"
            # cmd_path = "notepad.exe"
            # cmd_path = "clip.exe"
            cmd_args = [temp_img.name]

            if sys.platform == "win32":

                # Using subprocess.run hangs up the event thread, but if we're
                # running on Windows, we cannot launch subprocesses on a Selector loop,
                # only a Proactor loop.  The end result is that we cannot do asyncio
                # subprocesses on the loop where this function is called, and we end
                # up blocking the loop waiting for the process to end.
                # Also subprocess.run will ignore a timeout cancellation caused by whatever
                # is calling on_push, so be careful with subprocess.run, and always
                # include your own timeout=xxx parameter.

                proc = subprocess.run([cmd_path] + cmd_args,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,
                                      timeout=10,
                                      encoding=ENCODING)
                stdout_txt = proc.stdout
                stderr_txt = proc.stderr
            else:
                proc = await asyncio.create_subprocess_exec(cmd_path, *cmd_args,
                                                            stdin=asyncio.subprocess.PIPE,
                                                            stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.PIPE)
                stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(input=b''),
                                                                  timeout=10)
                stdout_txt = stdout_data.decode(encoding=ENCODING)
                stderr_txt = stderr_data.decode(encoding=ENCODING)

            # Upload picture

            resp = await pb.async_upload_file_to_transfer_sh(temp_img.name)
            file_type = resp.get("file_type")
            file_url = resp.get("file_url")
            file_name = resp.get("file_name")

            # Provide a response
            dev_iden = recvd_push.get("source_device_iden")
            dev = await pb.async_get_device(iden=dev_iden)
            await pb.async_push_file(file_name=file_name, file_url=file_url, file_type=file_type,
                                     title="Imagesnap", body="{}\n{}".format(stdout_txt, stderr_txt).strip(),
                                     device=dev)
            print("File uploaded and pushed: {}".format(file_url))
        # except asyncio.CancelledError as ce:
        #     # print("CANCELLED!", ce)
        #     # traceback.print_tb(sys.exc_info()[2])
        #     raise ce
        #
        # except Exception as e:
        #     # print("Error:", e, file=sys.stderr)
        #     # traceback.print_tb(sys.exc_info()[2])
        #     raise e

        finally:
            os.remove(temp_img.name)
