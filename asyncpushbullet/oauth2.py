# -*- coding: utf-8 -*-

import asyncio
import sys
import webbrowser
from concurrent import futures

import aiohttp  # pip install aiohttp
from aiohttp import WSMsgType, web

from asyncpushbullet import PushbulletError
from asyncpushbullet.prefs import Prefs
from asyncpushbullet.websocket_server import WebServer, WebsocketHandler, WebHandler

OAUTH2_TOKEN_KEY = "oauth2_token"

__ASYNCPUSHBULLET_OAUTH2_CLIENT_ID__ = "wS8zyC2gTU1WiROYlll60vAkpq7DTwjU"  # This project is registered on Pushbullet
__OAUTH2_URL_TEMPLATE__ = "https://www.pushbullet.com/authorize?client_id={client_id}&redirect_uri=http%3A%2F%2Flocalhost%3A{port}%2Fpb_oauth2&response_type=token&scope=everything"
__OAUTH2_REDIRECT_PORT__ = 31772  # Thank you, random.org
__PREFS_FOR_OAUTH2__ = Prefs("asyncpushbullet", "net.iharder.asyncpushbullet")


def get_oauth2_key():
    token = __PREFS_FOR_OAUTH2__.get(OAUTH2_TOKEN_KEY)
    return token

def clear_oauth2_key():
    __PREFS_FOR_OAUTH2__.set(OAUTH2_TOKEN_KEY, None)

async def async_gain_oauth2_access():
    __PREFS_FOR_OAUTH2__.set(OAUTH2_TOKEN_KEY, None)
    port = __OAUTH2_REDIRECT_PORT__
    oauth2_url = __OAUTH2_URL_TEMPLATE__.format(client_id=__ASYNCPUSHBULLET_OAUTH2_CLIENT_ID__, port=port)

    server = WebServer(port=port)
    token = None
    try:
        queue = asyncio.Queue()
        oauth_handler = OauthResponseHandler(port=port)
        token_handler = RegisterTokenWebsocketHandler(queue)
        server.add_route("/pb_oauth2", oauth_handler)
        server.add_route("/register_token", token_handler)
        await server.start()

        # Open a web page for the user to authorize the app
        print("Experimental: Waiting for user to authenticate through their web browser...")
        webbrowser.open(oauth2_url)

        # Wait for token
        resp = await asyncio.wait_for(queue.get(), 120)
        ws = await queue.get()  # type: web.WebSocketResponse

        if isinstance(resp, PushbulletError):
            await ws.send_json({"success": False})
            raise resp
        else:
            token = resp  # type: str
            __PREFS_FOR_OAUTH2__.set(OAUTH2_TOKEN_KEY, token)
            print("Oauth2 token successfully retrieved.")
            await ws.send_json({"success": True})
            return token

    except futures.TimeoutError as te:
        print("Timed out.  Did the user forget to authenticate?", file=sys.stderr)

    except Exception as ex:
        # print("Oauth2 token was not retrieved.", ex)
        # print(ex, file=sys.stderr)
        pass

    finally:
        await server.shutdown()
        return token


def gain_oauth2_access():
    loop = asyncio.get_event_loop()
    token = loop.run_until_complete(async_gain_oauth2_access())
    return token


class OauthResponseHandler(WebHandler):
    HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Title</title>
    
    <meta charset="utf-8">
    <meta name="theme-color" content="#ecf0f0">
    <meta id="pushbullet-extension" name="extension" content="">
    <title>Pushbullet - Your devices working better together</title>
    <link href="https://pushbullet.com/css/pushbullet.css" rel="stylesheet">

    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">

    <script type="text/javascript">
var access_token = null;
var connection = null;
var WebSocket = WebSocket || MozWebSocket;
var port = """ + str(__OAUTH2_REDIRECT_PORT__) + """;
    
function connect() {
    if (window.location.hash) {
        // hash found
        var hash = window.location.hash.substring(1); // Puts hash in variable, and removes the  # character
        hash_words = hash.split("=");
        access_token = hash_words[1];
    } else {
        
        document.getElementById("approve_btn").innerHTML = "Failed!";
        document.getElementById("approve_btn").style.backgroundColor = "red";
        document.getElementById("detail").innerHTML = "" +
            "<p>Authentication and permission failed.</p>";
    }

  var serverUrl = "ws://" + window.location.hostname + ":" + port + "/register_token";
  connection = new WebSocket(serverUrl);

  connection.onopen = function(evt) {
        if( access_token != null ){
            resp = {""" + OAUTH2_TOKEN_KEY + """:access_token};
        } else {
            resp = {error:"Authentication failed."};
        }
        connection.send(JSON.stringify(resp));
  };

  connection.onmessage = function(evt) {
    var msg = JSON.parse(evt.data);
    if( msg.success ){
        document.getElementById("approve_btn").innerHTML = "Success!";
        document.getElementById("detail").innerHTML = "" +
            "<p>You should now be able to use the " +
            "command line tools without specifying an API key.</p>" +
            "<p>ONLY the tools on your computer have gained access--not " +
            "anything on github.com or elsewhere.</p>" + 
            "<p>You may safely close this page.</p>";
    } else {
        /*document.getElementById("approve_btn").innerHTML = "Failed!";*/
        /*document.getElementById("approve_btn").style.backgroundColor = "red";*/
        /*document.getElementById("detail").innerHTML = "Something went wrong: " + msg.error;*/
    }
  };
}
</script>    
</head>
<body onload="connect()">
<div id="onecup">
    <div id="errors"></div>
    <div class="agree-page" style="text-align:center">
        <div id="header" style="position:relative;min-width:440px;margin-bottom:0px"><img id="logo"
                                                                                          src="https://pushbullet.com/img/header/logo@2x.png"
                                                                                          height="58px" width="306px"
                                                                                          style="position:absolute;top:15px;left:15px">
            
        </div>
        <div></div>
        <h1 style="margin:10px">AsyncPushbullet Command Line Tools on Your Computer</h1>
        <p style="width:400px;margin:15px auto 20px auto;line-height:34px;font-size:22px">Grant <strong><a
                href="https://github.com/rharder/asyncpushbullet">https://github.com/rharder/asyncpushbullet</a></strong>
            access to your Pushbullet profile and data.</p>
        <p>
            <button class="btn green approve" id="approve_btn"
                    style="width:230px;height:60px;font-size:20px;margin-bottom:30px">Approve
            </button>
        </p>
        <p id="detail"></p>
</div>
</div>
</body>
</html>
"""

    def __init__(self, port: int, *kargs, **kwargs):
        super().__init__(*kargs, **kwargs)
        self.port = port
        self.html = self.HTML

    async def on_incoming_http(self, route: str, request: web.BaseRequest):
        return web.Response(text=self.html, content_type="text/html")


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
                if OAUTH2_TOKEN_KEY in msg:
                    token = msg.get(OAUTH2_TOKEN_KEY)
                    await self.queue.put(token)
                else:
                    err = msg.get("error")
                    await self.queue.put(PushbulletError(err))

                await self.queue.put(ws)
