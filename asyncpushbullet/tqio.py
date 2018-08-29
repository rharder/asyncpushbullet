# -*- coding: utf-8 -*-
"""
Show upload progress using tqdm and aiohttp.
Example in tqio_upload_progress.py.

PasteBin: http://pastebin.com/ksEfNJZN
Source: https://github.com/rharder/handy
"""
import io
import os
import time

from tqdm import tqdm  # pip install tqdm

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"
__license__ = "Public Domain"


class tqio(io.BufferedReader):
    SLOW_DELAY = 0.1

    def __init__(self, file_path, descr=None, slow_it_down=False):
        super().__init__(open(file_path, "rb"))
        print(end="", flush=True)  # Flush output buffer to help tqdm
        self.t = tqdm(desc=descr,
                      unit="bytes",
                      unit_scale=True,
                      total=os.path.getsize(file_path))

        # Artificially slow down transfer for illustration
        self.slow_it_down = slow_it_down

    def __enter__(self):
        print(end="", flush=True)  # Flush output buffer to help tqdm
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def read(self, *args, **kwargs):
        if self.slow_it_down:
            chunk = super().read(64)
            self.t.update(len(chunk))
            time.sleep(self.SLOW_DELAY)
            return chunk
        else:
            # Keep these three lines after getting
            # rid of slow-it-down code for illustration.
            chunk = super().read(*args, **kwargs)
            self.t.update(len(chunk))
            return chunk


    def readline(self, *args, **kwargs):
        line = super().readline(*args, **kwargs)
        self.t.update(len(line))
        if self.slow_it_down:
            time.sleep(self.SLOW_DELAY)
        return line

    def close(self, *args, **kwargs):
        self.t.close()
        super().close()


