import asyncio
import logging
import os
import sys
import traceback
import webbrowser
from typing import Callable

import aiohttp
from aiohttp import WSMsgType, web

from asyncpushbullet.prefs import Prefs
from asyncpushbullet.websocket_server import WebServer, WebsocketHandler, WebHandler

logging.basicConfig(level=logging.DEBUG)

with open("../api_key.txt") as f:
    API_KEY = f.read().strip()

ASYNCPUSHBULLET_OAUTH2_CLIENT_ID = "wS8zyC2gTU1WiROYlll60vAkpq7DTwjU"
OAUTH2_URL = "https://www.pushbullet.com/authorize?client_id={}&redirect_uri=http%3A%2F%2Flocalhost%3A9999%2Fpb_oauth2&response_type=token&scope=everything".format(
    ASYNCPUSHBULLET_OAUTH2_CLIENT_ID)

API_KEY = API_KEY
PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")
prefs = Prefs("asyncpushbullet", "net.iharder.asyncpushbullet")


def main():
    def _callback(token):
        print("main received token:", token)
        # raise Exception("Any old problem at all!")

    gain_oauth2_access(_callback)


def gain_oauth2_access(token_callback: Callable):
    async def _run():
        try:
            queue = asyncio.Queue()
            server = WebServer(port=9999)
            oauth_handler = OauthResponseHandler()
            token_handler = RegisterTokenWebsocketHandler(queue)
            server.add_route("/pb_oauth2", oauth_handler)
            server.add_route("/register_token", token_handler)
            await server.start()

            # Open a web page for the user to authorize the app
            print("Awaiting user to authenticate through their web browser...")
            webbrowser.open(OAUTH2_URL)

            # We await on the queue until we get a token
            # TODO: PROBABLY NEED A TIMEOUT HERE
            token = await queue.get()  # type: str
            print("Got token from queue:", token)

            ws = await queue.get()  # type: web.WebSocketResponse
            try:
                token_callback(token)
            except Exception as ce:
                resp = {"success": False, "error": str(ce)}
                await ws.send_json(resp)
            else:
                resp = {"success": True}
                await ws.send_json(resp)

            await server.shutdown()
            return token

        except Exception as ex:
            print(ex, file=sys.stderr)
            tb = sys.exc_info()[2]
            traceback.print_tb(tb)

    loop = asyncio.get_event_loop()
    token = loop.run_until_complete(_run())
    print("Got token from the loop:", token)
    return token


class OauthResponseHandler(WebHandler):
    HTML = """<html>
<head>
    <title>AsyncPushbullet OAuth2</title>
    <script type="text/javascript">
var access_token = null;
var connection = null;
var WebSocket = WebSocket || MozWebSocket;

function connect() {

    if (window.location.hash) {
        var hash = window.location.hash.substring(1); // Puts hash in variable, and removes the  # character
        hash_words = hash.split("=");

        access_token = hash_words[1];
        console.log(access_token);
        // hash found

    } else {
        // No hash found
    }


  var serverUrl = "ws://" + window.location.hostname + ":9999/register_token";
  connection = new WebSocket(serverUrl);

  connection.onopen = function(evt) {
        document.getElementById("detail").value = access_token;
        resp = {token:access_token};
        connection.send(JSON.stringify(resp));
  };

  connection.onmessage = function(evt) {
    var msg = JSON.parse(evt.data);
    if( msg.success){
        document.getElementById("detail").value = "Success!";
    } else {
        document.getElementById("detail").value = "Something went wrong: " + msg.error;
    }
  };

  connection.onclose = function(evt) {
    document.getElementById("detail").value = 
      document.getElementById("detail").value + "\\n\\nDisconnected.";
  };

}

function send() {
  var msg = { detail: document.getElementById("detail").value };
  connection.send(JSON.stringify(msg));
}

function handleKey(evt) {
  if (evt.keyCode === 13 || evt.keyCode === 14) {
      send();
  }
}
    </script>
</head>
<body onload="connect()">
<p>Type and hit Enter to send text</p>
<textarea id="detail"  rows="10" cols="40"></textarea>
</body>
</html>
"""

    async def on_incoming_http(self, route: str, request: web.BaseRequest):
        return web.Response(text=self.HTML, content_type="text/html")


class RegisterTokenWebsocketHandler(WebsocketHandler):

    def __init__(self, queue: asyncio.Queue, *kargs, **kwargs):
        super().__init__(*kargs, **kwargs)
        self.queue = queue

    async def on_message(self, route: str, ws: web.WebSocketResponse, ws_msg_from_client: aiohttp.WSMessage):
        if ws_msg_from_client.type == WSMsgType.TEXT:
            try:
                msg = ws_msg_from_client.json()
            except Exception as ex:
                print("Error trying to make json", ex, ws_msg_from_client)
            else:
                if "token" in msg:
                    token = msg.get("token")
                    print("Token received!", token)
                    await self.queue.put(token)
                    await self.queue.put(ws)


if __name__ == "__main__":
    main()
