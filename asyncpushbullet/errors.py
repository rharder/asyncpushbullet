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


class InvalidKeyError(PushbulletError):
    pass

