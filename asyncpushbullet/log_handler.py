# -*- coding: utf-8 -*-
"""Python log handler that publishes to Pushbullet"""
import asyncio
import logging
import os

from asyncpushbullet import AsyncPushbullet, Pushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"


class PushbulletLogHandler(logging.Handler):
    """
    A handler for logging calls that sends log messages over pushbullet.

    Example:

        api_key = os.environ["PUSHBULLET_API_KEY"].strip()
        pb = AsyncPushbullet(api_key=api_key)
        handler = AsyncPushbulletLogHandler(pb, level=logging.WARNING)
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        logger.info("Normal stuff here.")
        logger.warning("Warning stuff here.")


    """

    def __init__(self, pushbullet: Pushbullet, level=logging.NOTSET):
        """
        Initialize the handler.
        """
        super().__init__(level=level)
        self.pushbullet: Pushbullet = pushbullet
        formatter = logging.Formatter('%(asctime)s\n%(levelname)s\n%(message)s')
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord):
        """
        Emit a record.
        """
        try:
            title = f"{record.name}:: {record.getMessage()}"
            body = self.format(record)
            self.pushbullet.push_note(title=title, body=body)

        except RecursionError:  # See issue 36272
            raise
        except Exception:
            self.handleError(record)

    def __repr__(self):
        level = logging.getLevelName(self.level)
        return '<%s (%s)>' % (self.__class__.__name__, level)


class AsyncPushbulletLogHandler(PushbulletLogHandler):

    def __init__(self, pushbullet: AsyncPushbullet, level=logging.NOTSET, use_first_available_loop: bool = True):
        """
        Initialize the handler with the given AsyncPushbullet object and logging level.
        If use_first_available_loop is true (default), then the first time the log handler
        is invoked, if it is running from an active event loop, that event loop will be the
        one on which the AsyncPushbullet makes its connections.  In the unusual case that you
        have more than one event loop running (different threads of course), then you may
        want to call the AsyncPushbullet aio_session() or connect() functions on the loop
        you intend it to run on.
        :param pushbullet:
        :param level:
        :param use_first_available_loop:
        """
        super().__init__(pushbullet=pushbullet, level=level)
        self.pushbullet: AsyncPushbullet = pushbullet
        self.use_first_available_loop: bool = bool(use_first_available_loop)

    def emit(self, record: logging.LogRecord):
        """
        Emit a record.
        """
        try:
            # If there is no loop yet known for the AsyncPushbullet object,
            # then we may need to grab the current running loop if there is one.
            if self.pushbullet.loop is None:
                if self.use_first_available_loop and asyncio.get_event_loop().is_running():
                    fut = asyncio.get_event_loop().create_task(self.pushbullet.aio_session())
                    fut.add_done_callback(lambda f: self.emit(record))
                else:
                    super().emit(record)  # synchronous version
            else:
                title = f"{record.name}: {record.getMessage()}"
                body = self.format(record)
                coro = self.pushbullet.async_push_note(title=title, body=body)
                asyncio.run_coroutine_threadsafe(coro, loop=self.pushbullet.loop)

        except RecursionError:  # See issue 36272
            raise
        except Exception:
            self.handleError(record)

    def __repr__(self):
        level = logging.getLevelName(self.level)
        return '<%s (%s)>' % (self.__class__.__name__, level)


def main():
    # Just an example
    async def run():
        api_key = os.environ["PUSHBULLET_API_KEY"].strip()
        # pb = await AsyncPushbullet(api_key=api_key).connect()
        pb = AsyncPushbullet(api_key=api_key)
        handler = AsyncPushbulletLogHandler(pb, level=logging.WARNING)
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        logger.info("Normal stuff here.")
        logger.warning("Warning stuff here.")
        logger.warning("Warning 2")

        print("Done")
        await asyncio.sleep(2)

    asyncio.get_event_loop().run_until_complete(run())


if __name__ == '__main__':
    main()
