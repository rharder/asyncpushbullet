asyncpushbullet
===============

.. http://rst.ninjs.org/ Online reStructuredText editor

.. image:: https://img.shields.io/pypi/pyversions/asyncpushbullet.svg
    :target: https://pypi.python.org/pypi/asyncpushbullet
    :alt: Python versions supported

.. image:: https://img.shields.io/pypi/v/asyncpushbullet.svg
    :target: https://pypi.python.org/pypi/asyncpushbullet
    :alt: current version on PyPI

.. image:: https://img.shields.io/travis/rharder/asyncpushbullet.svg?style=flat-square
    :target: https://travis-ci.org/rharder/asyncpushbullet
    :alt: build status

This is a python library for synchronous and asyncio-based
communication with the wonderful
`Pushbullet <https://www.pushbullet.com>`__ service. It allows you to
send push notifications to your computer,
`Android <https://play.google.com/store/apps/details?id=com.pushbullet.android>`__,
and `iOS <https://itunes.apple.com/us/app/pushbullet/id810352052>`__
devices.

In order to use the API you need an API key that can be obtained
`here <https://www.pushbullet.com/account>`__. This is user specific and
is used instead of passwords.

This is a fork of the synchronous-only
`pushbullet.py <https://github.com/randomchars/pushbullet.py>`__
project from randomchars, which uses the ``pushbullet`` namespace.
This project uses ``asyncpushbullet``.

Installation
------------

The easiest way is to just open your favorite terminal and type ::

    pip install asyncpushbullet

Alternatively you can clone this repo and install it with ::

    python setup.py install

Requirements
------------

-  The wonderful ``requests`` library.
-  The magical ``python-magic`` library.
-  The amazing ``aiohttp`` library
-  The optional (used in some examples) ``pillow`` library

Usage
-----

Command Line (optional)
~~~~~~~~~~~~~~~~~~~~~~~

The ``asyncpushbullet`` package has some scripts that can be run from the
command line.  One is for sending pushes.  One is for listening for and
responding to pushes.

There are three ways to authenticate your Pushbullet.com API key when using
the command line:

    1. Set the ``PUSHBULLET_API_KEY`` environment variable.
    2. Use the ``--key`` command line option and include the key as an argument.
    3. Use the ``--key-file`` command line option and point to a text file
       containing the API key.


Pushing a Note from the Command Line
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can push a note from the command line and specify a title and body. ::

    $ python3 -m asyncpushbullet.push --title "Hello World" --body "nothing to see"

Uploading and Pushing a File from the Command Line
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can upload and push a file as well. ::

    $ python3 -m asyncpushbullet.push --file homework.txt --title "Homework" --body "Avoid the dog."

The flags available for the ``push`` command line script: ::

    usage: push.py [-h] [-k KEY] [--key-file KEY_FILE] [-t TITLE] [-b BODY]
                   [-d DEVICE] [-u URL] [-f FILE] [--transfer.sh] [--list-devices]
                   [-q]

    optional arguments:
      -h, --help            show this help message and exit
      -k KEY, --key KEY     Your Pushbullet.com API key
      --key-file KEY_FILE   Text file containing your Pushbullet.com API key
      -t TITLE, --title TITLE
                            Title of your push
      -b BODY, --body BODY  Body of your push (- means read from stdin)
      -d DEVICE, --device DEVICE
                            Destination device nickname
      -u URL, --url URL     URL of link being pushed
      -f FILE, --file FILE  Pathname to file to push
      --transfer.sh         Use transfer.sh website for uploading files (use with
                            --file)
      --list-devices        List registered device names
      -q, --quiet           Suppress all output


Listening for and Responding to Pushes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can listen for pushes and respond.  To simply echo pushes to the console: ::

    $ python3 -m asyncpushbullet.listen --echo

You can have a script called whenever a push arrives.  The ``--exec`` flag takes its following
arguments as a script to call and any parameters to pass that script.  The script will be
called with those parameters and with the push (json encoded) sent via ``stdin``. ::

    $ python3 -m asyncpushbullet.listen --exec handle_new_push.sh

You can even have multiple actions listed at one time: ::

    $ python3 -m asyncpushbullet.listen --exec handle_new_push.sh  --exec record_in_log.sh

Your script can respond via its ``stdout`` in order to send push(es) back.  An example response: ::

    {
        "pushes" :
            [
                {
                    "title" = "Fish Food Served",
                    "body" = "Your automated fish feeding gadget has fed your fish. "
                 }
            ]
    }

Or if you only want to send one push, there is a simpler form for your response: ::

    { "title" = "title here", "body" = "body here"}

Finally instead of ``--exec``, you can use ``--exec-simple`` to skip json altogether.
Your script will receive the push via ``stdin`` except that the first line will be the
title of the push, and the subsequent lines will be the body. ::

    $ python3 -m asyncpushbullet.listen --exec-simple handle_new_push.sh

You can throttle how many pushes are received in a period of time using
the ``--throttle-count`` and ``--throttle-seconds`` flags.

The flags available for the ``listen`` command line script: ::

    usage: listen.py [-h] [-k KEY] [--key-file KEY_FILE] [-e] [-x EXEC [EXEC ...]]
                     [-s EXEC_SIMPLE [EXEC_SIMPLE ...]]
                     [--throttle-count THROTTLE_COUNT]
                     [--throttle-seconds THROTTLE_SECONDS] [-d DEVICE]
                     [--list-devices] [--debug] [-v]

    optional arguments:
      -h, --help            show this help message and exit
      -k KEY, --key KEY     Your Pushbullet.com API key
      --key-file KEY_FILE   Text file containing your Pushbullet.com API key
      -e, --echo            ACTION: Echo push as json to stdout
      -x EXEC [EXEC ...], --exec EXEC [EXEC ...]
                            ACTION: Execute a script to receive push as json via
                            stdin. Your script can write json to stdout to send
                            pushes back. { "pushes" : [ { "title" = "Fish Food
                            Served", "body" = "Your automated fish feeding gadget
                            has fed your fish. " } ] } Or simpler form for a
                            single push: { "title" = "title here", "body" = "body
                            here"}
      -s EXEC_SIMPLE [EXEC_SIMPLE ...], --exec-simple EXEC_SIMPLE [EXEC_SIMPLE ...]
                            ACTION: Execute a script to receive push in simplified
                            form via stdin. The first line of stdin will be the
                            title, and subsequent lines will be the body. Your
                            script can write lines back to stdout to send a single
                            push back. The first line of stdout will be the title,
                            and subsequent lines will be the body.
      --throttle-count THROTTLE_COUNT
                            Pushes will be throttled to this many pushes (default
                            10) in a certain number of seconds (default 10)
      --throttle-seconds THROTTLE_SECONDS
                            Pushes will be throttled to a certain number of pushes
                            (default 10) in this many seconds (default 10)
      -d DEVICE, --device DEVICE
                            Only listen for pushes targeted at given device name
      --list-devices        List registered device names
      --debug               Turn on debug logging
      -v, --verbose         Turn on verbose logging (INFO messages)



Developer Docs
~~~~~~~~~~~~~~

The following instructions relate to using ``asyncpushbullet`` within
your own Python code.

Authentication
^^^^^^^^^^^^^^

To create an ``AsyncPushbullet`` object: ::

    from asyncpushbullet import AsyncPushbullet
    pb = AsyncPushbullet(api_key)

If your key is invalid (that is, the Pushbullet API returns a ``401``),
an ``InvalidKeyError`` is raised the first time communication is made.
To check right away for the validity of your key, you can use the
``verify_key()`` or ``async_verify_key()`` functions,
in synchronous or asynchronous mode as appropriate. ::


    from asyncpushbullet import AsyncPushbullet
    pb = AsyncPushbullet(api_key)
    pb.verify_key()

or ::


    from asyncpushbullet import AsyncPushbullet
    pb = AsyncPushbullet(api_key)

    ...

    async def _run():
        await pb.verify_key()
        # do whatever

    loop.create_task(_run())


Event Loops
^^^^^^^^^^^

``AsyncPushbullet`` coroutines will work on whichever event loop they
are called from.  If you call from multiple event loops, you may need
to use the ``close_all()`` function when your program shuts down to
shutdown gracefully on all event loops.


Using a proxy
^^^^^^^^^^^^^
When specified, all requests to the API will be made through the proxy.
Note that the use of SOCKS proxies requires the ``requests[socks]`` package
(``pip install requests[socks]`` to install), however HTTP proxies (w/ Basic Auth)
work fine without the ``requests[socks]`` package.

**Proxy support is untested in this new async version**

::

    from asyncpushbullet import AsyncPushbullet
    pb = AsyncPushbullet(api_key, proxy={"https": "https://user:pass@10.10.1.10:3128/"})

Note that only HTTPS proxies work with Pushbullet.


Pushing a text note
^^^^^^^^^^^^^^^^^^^

::

    push = await pb.async_push_note("This is the title", "This is the body")

``push`` is a dictionary containing the data returned by the Pushbullet API.

Pushing an address
^^^^^^^^^^^^^^^^^^

Pushing addresses is no longer supported by pushbullet.com and has been dropped in ``asyncpushbullet``.

Pushing a list
^^^^^^^^^^^^^^

Pushing lists is no longer supported by pushbullet.com and has been dropped in ``asyncpushbullet``.

Pushing a link
^^^^^^^^^^^^^^

::

    push = await pb.async_push_link("Cool site", "https://github.com")

Pushing a file
^^^^^^^^^^^^^^

Pushing files is a two part process.  First you need to upload the file, and after that
you can push it like you would anything else.

::

    async def upload_my_file(pb: AsyncPushbullet, filename: str):
        info = await pb.async_upload_file(filename)

        # Push as a file:
        await pb.async_push_file(info["file_name"], info["file_url"], info["file_type"],
                                 title="File Arrived!", body="Please enjoy your file")

        # or Push as a link:
        await pb.async_push_link("Link to File Arrived!", info["file_url"], body="Please enjoy your file")

``async_upload_file()`` returns a dictionary containing  ``file_type``, ``file_url`` and ``file_name`` keys,
which are the same parameters that ``async_push_file()`` requires.

Working with pushes
^^^^^^^^^^^^^^^^^^^

You can also view all previous pushes: ::

    pushes = await pb.async_get_pushes()

Pushes is a list containing dictionaries that have push data.
You can use this data to dismiss notifications or delete pushes. ::

    latest = pushes[0]

    # We already read it, so let's dismiss it
    await pb.async_dismiss_push(latest.get("iden"))

    # And you can delete it
    await pb.async_delete_push(latest.get("iden"))

Both of these raise ``PushbulletError`` if there's an error.

You can also delete all of your pushes (**be careful**): ::

    await pb.async_delete_pushes()


Pushing to specific devices
^^^^^^^^^^^^^^^^^^^^^^^^^^^

So far all our pushes went to all connected devices, but there's a way to limit that.

First we need to get hold of some devices.

.. code:: python

    # Get all devices that the current user has access to.
    print(pb.devices)
    # [Device('Motorola Moto G'), Device('N7'), Device('Chrome')]

    # Select a device from the array using indexing
    motog = pb.devices[0]

    # Or retrieve a device by its name. Note that an InvalidKeyError is raised if the name does not exist
    motog = pb.get_device('Motorola Moto G')

Now we can use the device objects like we did with `pb`:

.. code:: python

    push = motog.push_note("Hello world!", "We're using the api.")

Alternatively we can pass the device to push methods:

.. code:: python

    push = pb.push_note("Hello world!", "We're using the api.", device=motog)

Creating new devices
^^^^^^^^^^^^^^^^^^^^

Creating a new device is easy too, you only need to specify a name for it.
Though you can also specify manufacturer, model and icon too.

.. code:: python

    listener = pb.new_device("Listener")
    motog = pb.new_device("MotoG", manufacturer="Motorola", model="G", icon="android")


Now you can use it like any other device.

Editing devices
^^^^^^^^^^^^^^^

You can change the nickname, the manufacturer, model and icon of the device:

.. code:: python

    listener = pb.edit_device(listener, manufacturer="Python", model="3.4.1", icon="system")
    motog = pb.edit_device(motog, nickname="My MotoG")


Deleting devices
^^^^^^^^^^^^^^^^

Of course, you can also delete devices, even those not added by you.

.. code:: python

    pb.remove_device(listener)

A ``PushbulletError`` is raised on error.

Channels
^^^^^^^^

You can also send pushes to channels. First, create a channel on the Pushbullet
website (also make sure to subscribe to that channel). All channels which
belong to the current user can be retrieved as follows:

.. code:: python

    # Get all channels created by the current user
    print(pb.channels)
    # [Channel('My Channel' 'channel_identifier')]

    my_channel = pb.channels[0]

    # Or retrieve a channel by its channel_tag. Note that an InvalidKeyError is raised if the channel_tag does not exist
    my_channel = pb.get_channel('My Channel')

Then you can send a push to all subscribers of this channel like so:

.. code:: python

    push = my_channel.push_note("Hello Channel!", "Hello My Channel")

Alternatively we can pass the channel to push methods:

.. code:: python

    push = pb.push_note("Hello Channel!", "Hello My Channel.", channel=my_channel)

Note that you can only push to channels which have been created by the current
user.


Contacts
^^^^^^^^

Contacts, which are known as "Chats" in Pushbullet's terminilogy, work just like devices:

.. code:: python

    # Get all contacts the user has
    print(pb.chats)
    # [Chat('Peter' <peter@gmail.com>), Chat('Sophie' <sophie@gmail.com>)]

    sophie = pb.chats[1]

Now we can use the chat objects like we did with `pb` or with the devices.:

.. code:: python

    push = sophie.push_note("Hello world!", "We're using the api.")

    # Or:
    push = pb.push_note("Hello world!", "We're using the api.", chat=sophie)


Adding new chats
^^^^^^^^^^^^^^^^

.. code:: python

    bob = pb.new_chat("Bob", "bob@gmail.com")

Editing chats
^^^^^^^^^^^^^

You can change the name of any chat:

.. code:: python

    bob = pb.edit_chat(bob, "bobby")

Deleting chats
^^^^^^^^^^^^^^

.. code:: python

    pb.remove_chat(bob)


Sending SMS messages
^^^^^^^^^^^^^^^^^^^^

.. code:: python

    device = pb.devices[0]
    push = pb.push_sms(device, "+3612345678", "Wowza!")

End-To-End encryption
^^^^^^^^^^^^^^^^^^^^^

You activate end-to-end encryption by specifying your encryption key during the construction of the ``Pushbullet`` instance:

.. code:: python

    from pushbullet import Pushbullet

    pb = Pushbullet(api_key, "My secret password")

When specified, all sent SMS will be encrypted. Note that the use of end-to-end encryption requires the ``cryptography`` package. Since end-to-end encryption is only supported for SMS at the moment, the ``cryptography`` library is not specified as a dependency of ``pushbullet.py`` and should be installed seperatly by running ``pip install cryptography``.

Note that Pushbullet supportes End-To-End encryption only in SMS, notification mirroring and universal copy & paste. Your pushes will not be end-to-end encrypted.


Error checking
^^^^^^^^^^^^^^

If the Pushbullet api returns an error code a ``PushError`` an __
``InvalidKeyError`` or a ``PushbulletError`` is raised. The first __
two are both subclasses of ``PushbulletError``

The `pushbullet api documetation <https://www.pushbullet.com/api>`__
contains a list of possible status codes.

Asynchronous IO
^^^^^^^^^^^^^^^

Many of the same methods that are available in the Pushbullet class are available in a form
compatible with Python 3's ``asyncio`` features using AsyncPushbullet.

.. code:: python

    def __init__(self):
        self.apb = AsyncPushbullet("your api key here")
        # ...

.. code:: python

    async def some_method_you_have(self):
        dev = await self.apb.async_new_device("SomeCoolRobot")
        # ...

.. code:: python

    async def some_method_you_have(self):
        pushes = await self.apb.async_get_pushes(limit=5)
        # ...

.. code:: python

    async def some_method_you_have(self):

        async for p in PushListener(self.apb):
            print("New push received:", p)
            # ...

TODO
----

-  More tests. Write them all.

License
-------

MIT license. See LICENSE for full text.
