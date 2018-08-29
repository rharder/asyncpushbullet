# -*- coding: utf-8 -*-

def _magic_get_file_type(filename):
    with open(filename, "rb") as f:
        file_type = magic.from_buffer(f.read(1024), mime=True)
    return maybe_decode(file_type)


def _guess_file_type(filename):
    return mimetypes.guess_type(filename)[0]


# return str on python3.  Don't want to unconditionally
# decode because that results in unicode on python2
def maybe_decode(s):
    if str == bytes:
        return s.decode('utf-8')
    else:
        return s


try:
    import magic
except Exception:
    import mimetypes

    get_file_type = _guess_file_type
else:
    get_file_type = _magic_get_file_type
