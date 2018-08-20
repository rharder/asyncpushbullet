from __future__ import unicode_literals

import sys


def use_appropriate_encoding(fn):

    if sys.version_info[0] < 3:
        def _fn(*args, **kwargs):
            return fn(*args, **kwargs).encode(sys.stdout.encoding or 'utf-8')
        return _fn
    else:
        return fn

def print_function_name(enclosing_class=None):
    try:
        if enclosing_class is None:
            classname = ""
        elif isinstance(enclosing_class, str):
            classname = enclosing_class
        else:
            classname = enclosing_class.__class__.__name__
        import inspect
        name = inspect.getframeinfo(inspect.currentframe().f_back).function
        print('\033[94m{}.{}\033[99m'.format(classname, name), flush=True)
    except AttributeError as ae:
        raise ae
        pass  # Likely caused by lack of stack frame support where currentframe() returns None.
    except KeyError as ke:
        raise ke
        pass  # In case the function name is not found in the globals dictionary.
