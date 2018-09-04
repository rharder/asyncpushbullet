# -*- coding: utf-8 -*-

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

    def __init__(self, code, err_msg, msg, *kargs, **kwargs):
        super().__init__(code, err_msg, msg, *kargs, **kwargs)
        self.code = code
        self.err_msg = err_msg
        self.msg = msg


class InvalidKeyError(HttpError):
    pass
