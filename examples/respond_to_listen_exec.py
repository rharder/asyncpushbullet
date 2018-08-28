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
from asyncpushbullet import Pushbullet, AsyncPushbullet

__encoding__ = "utf-8"
API_KEY = ""  # YOUR API KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


def main():
      #   TEMP = """{'active': true,
      # 'awake_app_guids': ['web-vou977uqosgdtkfm00ohao'],
      # 'body': 'imagesnap',
      # 'created': 1535481590.9756641,
      # 'direction': 'self',
      # 'dismissed': false,
      # 'guid': '4hcb7mun0e85ov8as58uo8',
      # 'iden': 'ujzlLkPSZgqsjAyYJfiSLQ',
      # 'modified': 1535481590.982829,
      # 'receiver_email': 'robertharder@gmail.com',
      # 'receiver_email_normalized': 'robertharder@gmail.com',
      # 'receiver_iden': 'ujzlLkPSZgq',
      # 'sender_email': 'robertharder@gmail.com',
      # 'sender_email_normalized': 'robertharder@gmail.com',
      # 'sender_iden': 'ujzlLkPSZgq',
      # 'sender_name': 'Robert Harder',
      # 'target_device_iden': 'ujzlLkPSZgqsjz5ARsslR6',
      # 'type': 'note'}""".replace("'",'"')
      #   recvd_push = json.loads(TEMP)

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

            # Temp file to house the image file
            temp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            temp_img.close()

            try:

                # PRETEND TO TAKE A PICTURE
                fakepic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.jpg")
                shutil.copy(fakepic, temp_img.name)

                # Take a picture
                proc = subprocess.run(["imagesnap", f.name],
                # proc = subprocess.run(["notepad.exe", temp_img.name],
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)#,
                                      # timeout=30,
                                      # encoding=__encoding__)

                # Upload picture
                # pb = Pushbullet(API_KEY, proxy=PROXY)
                pb = AsyncPushbullet(API_KEY, proxy=PROXY, verify_ssl=False)
                resp = pb.upload_file(temp_img.name)
                file_type = resp.get("file_type")
                file_url = resp.get("file_url")
                file_name = resp.get("file_name")

                # Provide a response via stdout
                stdout_txt = proc.stdout.decode(__encoding__, "replace")
                stderr_txt = proc.stderr.decode(__encoding__, "replace")
                myresp = {
                    "type": "file",
                    "title": "Imagesnap",
                    "body": "{}\n{}".format(stdout_txt, stderr_txt).strip(),
                    "file_name": file_name,
                    "file_type": file_type,
                    "file_url": file_url,
                    "received_push": recvd_push
                }
                dev_iden = recvd_push.get("source_device_iden")
                if dev_iden is not None:
                    myresp["device_iden"] = dev_iden

                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "response.json"), "w") as fout:
                    fout.write(json.dumps(myresp, indent=4))

                print(json.dumps(myresp), flush=True)
            except Exception as e:
                raise e
                # print("Error:", e, file=sys.stderr)

            finally:

                os.remove(temp_img.name)


if __name__ == "__main__":

    if API_KEY == "":
        with open("../api_key.txt") as f:
            API_KEY = f.read().strip()

    main()
