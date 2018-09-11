# -*- coding: utf-8 -*-

# Exit codes used on command line
__EXIT_NO_ERROR__ = 0
__ERR_API_KEY_NOT_GIVEN__ = 1
__ERR_INVALID_API_KEY__ = 2
__ERR_CONNECTING_TO_PB__ = 3
__ERR_FILE_NOT_FOUND__ = 4
__ERR_DEVICE_NOT_FOUND__ = 5
__ERR_NOTHING_TO_DO__ = 6
__ERR_KEYBOARD_INTERRUPT__ = 7
__ERR_UNKNOWN__ = 99


class PushbulletError(Exception):

    def __str__(self):
        newargs = []
        for arg in self.args:
            if isinstance(arg, BaseException):
                newargs += [arg.__class__.__name__, str(arg)]
            else:
                newargs.append(str(arg))

        s = "{}: {}".format(self.__class__.__name__, " ".join(newargs))
        return s


class HttpError(PushbulletError):

    def __init__(self, code, err_msg, pushbullet_msg, *kargs, **kwargs):
        super().__init__(code, err_msg, pushbullet_msg, *kargs, **kwargs)
        self.code = code
        self.err_msg = err_msg
        self.pushbullet_msg = pushbullet_msg


class InvalidKeyError(HttpError):
    pass
