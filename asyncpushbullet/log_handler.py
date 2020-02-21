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
        self.pushbullet = pushbullet
        formatter = logging.Formatter('%(asctime)s\n%(levelname)s\n%(message)s')
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord):
        """
        Emit a record.
        """
        try:
            msg = self.format(record)
            title = f"{record.name}:: {record.getMessage()}"
            self.pushbullet.push_note(title=title, body=msg)

        except RecursionError:  # See issue 36272
            raise
        except Exception:
            self.handleError(record)

    def __repr__(self):
        level = logging.getLevelName(self.level)
        return '<%s (%s)>' % (self.__class__.__name__, level)


class AsyncPushbulletLogHandler(PushbulletLogHandler):

    def __init__(self, pushbullet: AsyncPushbullet, level=logging.NOTSET):
        """
        Initialize the handler.
        """
        super().__init__(pushbullet=pushbullet, level=level)
        self.pushbullet: AsyncPushbullet = pushbullet

    def emit(self, record: logging.LogRecord):
        """
        Emit a record.
        """
        try:
            if self.pushbullet.loop is None:
                # print(
                #     "AsyncPushbullet has no event loop - has it connected at least once while in a loop? Using synchronous calls instead.")
                super().emit(record)
            else:
                msg = self.format(record)
                title = f"{record.name}: {record.getMessage()}"
                return asyncio.run_coroutine_threadsafe(
                    self.pushbullet.async_push_note(title=title, body=msg),
                    loop=self.pushbullet.loop)

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
        pb = AsyncPushbullet(api_key=api_key)
        handler = AsyncPushbulletLogHandler(pb, level=logging.WARNING)
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        logger.info("Normal stuff here.")
        logger.warning("Warning stuff here.")

        print("Done")
        await asyncio.sleep(2)

    asyncio.get_event_loop().run_until_complete(run())


if __name__ == '__main__':
    main()
