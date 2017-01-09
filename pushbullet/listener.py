import asyncio
from pprint import pprint

import aiohttp

__author__ = 'Igor Maculan <n3wtron@gmail.com>'

import logging
import time
import json
# from threading import Thread

# import requests
# import websockets  # https://github.com/aaugustin/websockets

log = logging.getLogger('pushbullet.Listener')

WEBSOCKET_URL = 'wss://stream.pushbullet.com/websocket/'


class Listener():
    def __init__(self, account,
                 on_push=None,
                 on_error=None):#,
                 # http_proxy_host=None,
                 # http_proxy_port=None):
        """
        :param api_key: pushbullet Key
        :param on_push: function that get's called on all pushes
        :param http_proxy_host: host proxy (ie localhost)
        :param http_proxy_port: host port (ie 3128)
        """
        self._account = account
        self._api_key = self._account.api_key
        self.on_error = on_error

        self.connected = False
        self.last_update = time.time()

        self.on_push = on_push

        # History
        self.history = None
        self.clean_history()

        # proxy configuration
        # self.http_proxy_host = http_proxy_host
        # self.http_proxy_port = http_proxy_port
        # self.proxies = None
        # if http_proxy_port is not None and http_proxy_port is not None:
        #     self.proxies = {
        #         "http": "http://" + http_proxy_host + ":" + str(http_proxy_port),
        #         "https": "http://" + http_proxy_host + ":" + str(http_proxy_port),
        #     }

    def clean_history(self):
        self.history = []

    def on_open(self, ws):
        log.debug("on_open")
        self.connected = True
        self.last_update = time.time()

    def on_close(self, ws):
        log.debug('Listener closed')
        self.connected = False

    async def on_message(self, ws, msg):
        log.debug('Message received:' + str(msg))
        try:
            if msg["type"] != "nop" and callable(self.on_push):
                await self.on_push(msg)
        except Exception as e:
            logging.exception(e)

    def connect(self):
        asyncio.ensure_future(self._ws_monitor())

    async def _ws_monitor(self):
        """
        Begins listening to the websocket on an event loop.

        Example:
            asyncio.ensure_future(listener.connect())
        """
        async with self._account._aio_session.ws_connect(WEBSOCKET_URL + self._api_key) as ws:
            self.on_open(ws)
            async for msg in ws:
                self.last_update = time.time()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.on_message(ws, json.loads(msg.data))
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.on_close(ws)
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break

            # except websockets.ConnectionClosed as ex:
            #     self.on_close(ws)
            # except Exception as ex:
            #     if callable(self.on_error):
            #         self.on_error(ws, ex)
            #     else:
            #         raise ex

    # def run_forever(self, sockopt=None, sslopt=None, ping_interval=0, ping_timeout=None):
    #     websocket.WebSocketApp.run_forever(self, sockopt=sockopt, sslopt=sslopt, ping_interval=ping_interval,
    #                                        ping_timeout=ping_timeout,
    #                                        http_proxy_host=self.http_proxy_host,
    #                                        http_proxy_port=self.http_proxy_port)

    # def run(self):
    #     self.run_forever()
