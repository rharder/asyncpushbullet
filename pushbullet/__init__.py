from .__version__ import __version__
from .pushbullet import Pushbullet
from .device import Device
from .errors import PushbulletError, InvalidKeyError, PushError

try:
    from .listener import Listener
except Exception as e:
    import logging
    log = logging.getLogger("pushbullet")
    log.warning("Problem loading the synchronous Listener: {}".format(e))

# Async requires Python 3.5+ and aiohttp
try:
    from .async_pushbullet import AsyncPushbullet
    from .async_listeners import WebsocketListener, PushListener
except Exception as e:
    import logging
    log = logging.getLogger("pushbullet")
    log.warning("Problem loading the asynchronous classes: {}".format(e))


PushBullet = Pushbullet
