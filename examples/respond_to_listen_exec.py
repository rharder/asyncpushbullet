#!/usr/bin/env python3
import asyncio
import io
import json
import os
import sys
import threading
import tkinter as tk
from functools import partial

from asyncpushbullet import AsyncPushbullet, Pushbullet

__encoding__ = "utf-8"
API_KEY = ""  # YOUR API KEY


def main():
    # print("I heard you")
    # with io.open(sys.stdin.fileno(), mode="r", encoding="utf-8") as f:
    #     stdin = f.read()
    #     stdin_from_json = json.loads(stdin)
    #     print("WHAT I GOT: <<<{}>>>".format(json.dumps(stdin_from_json)))

    proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
    pb = Pushbullet(API_KEY, proxy=proxy)

    resp = pb.upload_file(__file__)
    file_type = resp.get("file_type")
    file_url = resp.get("file_url")
    file_name = resp.get("file_name")
    myresp = {
        "type": "file",
        "title": "Test File",
        "body": "Something about this file",
        "file_name": file_name,
        "file_type": file_type,
        "file_url": file_url
    }
    print(json.dumps(myresp))

    # tk1 = tk.Tk()
    # tk1.title("Pushbullet Account Management")
    # tk1.mainloop()


def main2():
    async def _on_proc_loop():
        print("_on_proc_loop")
        try:
            push = json.loads(
                """{"active": true, "iden": "ujzlLkPSZgqsjAh3AV3rNs", "created": 1535400074.852171, "modified": 1535400074.859157, "type": "note", "dismissed": false, "guid": "fc8f1demd18jicpu85a4jo", "direction": "self", "sender_iden": "ujzlLkPSZgq", "sender_email": "robertharder@gmail.com", "sender_email_normalized": "robertharder@gmail.com", "sender_name": "Robert Harder", "receiver_iden": "ujzlLkPSZgq", "receiver_email": "robertharder@gmail.com", "receiver_email_normalized": "robertharder@gmail.com", "target_device_iden": "ujzlLkPSZgqsjz5ARsslR6", "awake_app_guids": ["web-vou977uqosgdtkfm00ohao"], "body": "foo"}""")

            cmd = r"c:\python37-32\python.exe"
            args = [r"C:\Users\rharder\Documents\Programming\asyncpushbullet\examples\hello.py"]

            print("Executing", cmd, *args)
            proc = await asyncio.create_subprocess_exec(cmd,
                                                        *args,
                                                        stdin=asyncio.subprocess.PIPE,
                                                        stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.PIPE)

            json_push = json.dumps(push)
            input_bytes = json_push.encode(__encoding__)
        except Exception as e:
            print("Exception:", e)

        try:
            stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(input=input_bytes),
                                                              timeout=10)
        except asyncio.futures.TimeoutError as e:
            print("Timeout error", e)
            proc.terminate()
        else:
            # Process response from subprocess
            # asyncio.run_coroutine_threadsafe(
            #     handle_process_response(stdout_data, stderr_data),
            #     loop=io_loop)
            print("stdout", stdout_data)
            print("stderr", stderr_data)
            pass

    def _run(loop):
        print("_run")
        asyncio.set_event_loop(loop)
        loop.run_forever()

    io_loop = asyncio.new_event_loop()
    proc_loop = asyncio.ProactorEventLoop()
    threading.Thread(target=partial(_run, proc_loop), name="Thread-proc", daemon=False).start()
    asyncio.run_coroutine_threadsafe(_on_proc_loop(), proc_loop)
    # io_loop.run_forever()


async def handle_process_response(self, stdout_data: bytes, stderr_data: bytes):
    # stdout_data = b"hello world"
    # await asyncio.sleep(1)

    # There's a problem with a push be sent in response and then that push is responded
    # to etc and then an infinite loop.

    # raise Exception("Not yet implemented.")

    # Any stderr output?
    if stderr_data != b"":
        self.log.error("Error from {}: {}".format(repr(self), stderr_data))

    # Any stdout output?
    if stdout_data != b"":
        self.log.info("Response from {}: {}".format(repr(self), stdout_data))

        # Requesting a response push?
        resp = {}
        raw_data = None
        try:
            raw_data = stdout_data.decode(__encoding__, "replace")
            resp = json.loads(raw_data)
        except json.decoder.JSONDecodeError as e:
            resp["body"] = raw_data

        # Single push response
        if "title" in resp or "body" in resp:
            title = str(resp.get("title"))
            body = str(resp.get("body"))
            # push_resp = await pb.async_push_note(title=title, body=body)
            # push_resp = await device.push_note(title=title, body=body)
            # print("Push Resp:", push_resp)

        # Multiple pushes response
        pushes = resp.get("pushes", [])
        if type(pushes) == list:
            for push in pushes:  # type: dict
                if type(push) == dict:
                    title = push.get("title", "no title")
                    body = push.get("body", "no body")
                    # await pb.async_push_note(title=title, body=body)
                else:
                    self.log.error("A push response was received but was not in dictionary form: {}".format(resp))
    pass
    pass
    print("exiting handle_process_response")
    pass


if __name__ == "__main__":

    if __name__ == "__main__":
        if API_KEY == "":
            with open("../api_key.txt") as f:
                API_KEY = f.read().strip()
        main()

    main()
