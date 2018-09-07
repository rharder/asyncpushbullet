asyncpushbullet
===============

.. http://rst.ninjs.org/ Online reStructuredText editor

.. image:: https://img.shields.io/pypi/pyversions/asyncpushbullet.svg
    :target: https://pypi.python.org/pypi/asyncpushbulletF
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
This project uses ``asyncpushbullet``.  I have made some changes to the
``pushbullet`` package, and you ought to be able to use the regular
synchronous functions alongside the ``asyncio``-enabled versions.
Over time these have drifter further apart, so if you drop in the
``asyncpushbullet`` package in place of an older ``pushbullet`` package,
you will probably need to make some changes to your code in terms of
function names and error handling.

Installation
------------

The easiest way is to just open your favorite terminal and type ::

    pip install asyncpushbullet

Alternatively you can clone this repo and install it with ::

    python setup.py install

Requirements
------------

-  ``requests``: Used in synchronous ``Pushbullet`` superclass
-  ``python-magic``: Guesses at filetypes for uploading, optional
-  ``aiohttp``: Foundational to the ``asyncio``-enabled ``AsyncPushbullet`` classes
-  ``tqdm``: For some command line scripts
-  ``pillow``: Used in some example GUI code

Usage
-----

Command Line (optional)
~~~~~~~~~~~~~~~~~~~~~~~

The ``asyncpushbullet`` package has some scripts that can be run from the
command line.  One is for sending pushes.  Two are for listening for and
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

    $ pbpush --title "Hello World" --body "nothing to see"

Uploading and Pushing a File from the Command Line
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can upload and push a file as well. ::

    $ pbpush --file homework.txt --title "Homework" --body "Avoid the dog."

The flags available for the ``pbpush`` command line script: ::

    usage: pbpush [-h] [-k KEY] [--key-file KEY_FILE] [--proxy PROXY] [-t TITLE]
                  [-b BODY] [-d DEVICE] [--list-devices] [-u URL] [-f FILE]
                  [--transfer.sh] [-q]

    optional arguments:
      -h, --help            show this help message and exit
      -k KEY, --key KEY     Your Pushbullet.com API key
      --key-file KEY_FILE   Text file containing your Pushbullet.com API key
      --proxy PROXY         Optional web proxy
      -t TITLE, --title TITLE
                            Title of your push
      -b BODY, --body BODY  Body of your push (- means read from stdin)
      -d DEVICE, --device DEVICE
                            Destination device nickname
      --list-devices        List registered device names
      -u URL, --url URL     URL of link being pushed
      -f FILE, --file FILE  Pathname to file to push
      --transfer.sh         Use www.transfer.sh website for uploading files (use
                            with --file)
      -q, --quiet           Suppress all output

There is also a variant of ``pbpush`` called ``pbtransfer`` that makes it even
faster and easier to send off files using the http://transfer.sh service. ::

    $ pbtransfer somefile.jpg someotherfile.mp4

The flags available for the ``pbtransfer`` command line script: ::

    usage: pbtransfer [-h] [-k KEY] [--key-file KEY_FILE] [--proxy PROXY]
                      [-d DEVICE] [--list-devices] [-f FILE] [-q]
                      [files [files ...]]

    positional arguments:
      files                 Remaining arguments will be files to push

    optional arguments:
      -h, --help            show this help message and exit
      -k KEY, --key KEY     Your Pushbullet.com API key
      --key-file KEY_FILE   Text file containing your Pushbullet.com API key
      --proxy PROXY         Optional web proxy
      -d DEVICE, --device DEVICE
                            Destination device nickname
      --list-devices        List registered device names
      -f FILE, --file FILE  Pathname to file to push
      -q, --quiet           Suppress all output



Listening for and Responding to Pushes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can listen for pushes and respond.  To simply echo pushes to the console: ::

    $ pblisten --echo

You can have a script called whenever a push arrives.  The ``--exec`` flag takes its following
arguments as a script to call and any parameters to pass that script.  The script will be
called with those parameters and with the push (json encoded) sent via ``stdin``. ::

    $ pblisten --exec handle_new_push.sh

You can even have multiple actions listed at one time: ::

    $ pblisten --exec handle_new_push.sh  --exec record_in_log.sh

Your script can respond via its ``stdout`` in order to send push(es) back.  An example response:

.. code-block:: json

        [
            {
                "title" : "Fish Food Served",
                "body" : "Your automated fish feeding gadget has fed your fish. "
             },
             { "title" : "Second push", "body" : "Second body" }
        ]

Or if you only want to send one push, there is a simpler form for your response:

.. code-block:: json

    { "title" : "title here", "body" : "body here"}

Finally instead of ``--exec``, you can use ``--exec-simple`` to skip json altogether.
Your script will receive the push via ``stdin`` except that the first line will be the
title of the push, and the subsequent lines will be the body. ::

    $ pblisten --exec-simple handle_new_push.sh

You can throttle how many pushes are received in a period of time using
the ``--throttle-count`` and ``--throttle-seconds`` flags.

If a device nickname is specified, and there is no device with that nickname,
a new device will be created with that nickname.

The flags available for the ``pblisten`` command line script: ::

    usage: pblisten [-h] [-k KEY] [--key-file KEY_FILE] [-e] [-x EXEC [EXEC ...]]
                    [-s EXEC_SIMPLE [EXEC_SIMPLE ...]]
                    [--throttle-count THROTTLE_COUNT]
                    [--throttle-seconds THROTTLE_SECONDS] [-d DEVICE]
                    [--list-devices] [--proxy PROXY] [--debug] [-v]

    optional arguments:
      -h, --help            show this help message and exit
      -k KEY, --key KEY     Your Pushbullet.com API key
      --key-file KEY_FILE   Text file containing your Pushbullet.com API key
      -e, --echo            ACTION: Echo push as json to stdout
      -x EXEC [EXEC ...], --exec EXEC [EXEC ...]
                            ACTION: Execute a script to receive push as json via
                            stdin. Your script can write json to stdout to send
                            pushes back. [ { "title" = "Fish Food
                            Served", "body" = "Your automated fish feeding gadget
                            has fed your fish. " } ]  Or simpler form for a
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
      --proxy PROXY         Optional web proxy
      --debug               Turn on debug logging
      -v, --verbose         Turn on verbose logging (INFO messages)



Developer Docs
~~~~~~~~~~~~~~

The following instructions relate to using ``asyncpushbullet`` within
your own Python code.

Quick Start
^^^^^^^^^^^

Here is a well-behaved example right off the bat to take a look at:

.. code-block:: python

    # !/usr/bin/env python3
    # -*- coding: utf-8 -*-
    import asyncio
    import os
    import sys

    from asyncpushbullet import AsyncPushbullet, InvalidKeyError, PushbulletError, LiveStreamListener

    API_KEY = "whatever your key is"
    PROXY = os.environ.get("https_proxy") or os.environ.get("http_proxy")


    def main():
        async def _run():
            try:
                async with AsyncPushbullet(API_KEY, proxy=PROXY) as pb:

                    # List devices
                    devices = await pb.async_get_devices()
                    print("Devices:")
                    for dev in devices:
                        print("\t", dev)

                    # Send a push
                    push = await pb.async_push_note(title="Success", body="I did it!")
                    print("Push sent:", push)

                    # Ways to listen for pushes
                    async with LiveStreamListener(pb) as pl:
                        # This will retrieve the previous push because it occurred
                        # after the enclosing AsyncPushbullet connection was made
                        push = await pl.next_push()
                        print("Previous push, now received:", push)

                        # Get pushes forever
                        print("Awaiting pushes forever...")
                        async for push in pl:
                            print("Push received:", push)



            except InvalidKeyError as ke:
                print(ke, file=sys.stderr)

            except PushbulletError as pe:
                print(pe, file=sys.stderr)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(_run())


    if __name__ == "__main__":
        main()

Authentication
^^^^^^^^^^^^^^

To create an ``AsyncPushbullet`` object:

.. code-block:: python

    from asyncpushbullet import AsyncPushbullet
    pb = AsyncPushbullet(api_key)

If your key is invalid (that is, the Pushbullet API returns a ``401``),
an ``InvalidKeyError`` is raised the first time communication is made.
To check right away for the validity of your key, you can use the
``verify_key()`` or ``async_verify_key()`` functions,
in synchronous or asynchronous mode as appropriate.

.. code-block:: python

    from asyncpushbullet import AsyncPushbullet
    ...
    pb = AsyncPushbullet(api_key)
    await pb.async_verify_key()
    ...
    await pb.async_close()

or even better -- **this is preferred** because it neatly closes sessions using
the ``async with`` context manager.

.. code-block:: python

    from asyncpushbullet import AsyncPushbullet

    ...

    async def _run():
        async with AsyncPushbullet(api_key) as pb:
            # Do stuff

    loop.create_task(_run())


Event Loops
^^^^^^^^^^^


``AsyncPushbullet`` expects its async functions to operate on only one event loop.
Create a new ``AsyncPushbullet`` object if you need to operate on multiple
event loops.  If you need to close an ``AsyncPushbullet`` from another loop
or thread, use the ``close_all_threadsafe()``.


Using a proxy
^^^^^^^^^^^^^
When specified, all requests to the API will be made through the proxy.

.. code-block:: python

    from asyncpushbullet import AsyncPushbullet
    pb = AsyncPushbullet(api_key, proxy="https://user:pass@10.10.1.10:3128/")


Pushing a text note
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

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

.. code-block:: python

    push = await pb.async_push_link("Cool site", "https://github.com")

Pushing a file
^^^^^^^^^^^^^^

Pushing files is a two part process.  First you need to upload the file, and after that
you can push it like you would anything else.

.. code-block:: python

    async def upload_my_file(pb: AsyncPushbullet, filename: str):
        # The actual upload
        info = await pb.async_upload_file(filename)

        # Push as a file:
        await pb.async_push_file(info["file_name"], info["file_url"], info["file_type"],
                                 title="File Arrived!", body="Please enjoy your file")

        # or Push as a link:
        await pb.async_push_link("Link to File Arrived!", info["file_url"], body="Please enjoy your file")

``async_upload_file()`` returns a dictionary containing  ``file_type``, ``file_url`` and ``file_name`` keys,
which are the same parameters that ``async_push_file()`` requires.

You can also upload a file to the https://transfer.sh service using ``async_upload_file_to_transfer_sh``.
The https://transfer.sh service allows file uploads up to 10GB in size, and links last only two weeks.

.. code-block:: python

    ...
    info = await pb.async_upload_file_to_transfer_sh(filename)
    ...

Working with pushes
^^^^^^^^^^^^^^^^^^^

You can also view all previous pushes:

.. code-block:: python

    pushes = await pb.async_get_pushes()

Pushes is a list containing dictionaries that have push data.
You can use this data to dismiss notifications or delete pushes.

.. code-block:: python

    latest = pushes[0]

    # We already read it, so let's dismiss it
    await pb.async_dismiss_push(latest.get("iden"))

    # And you can delete it
    await pb.async_delete_push(latest.get("iden"))

Both of these raise a ``PushbulletError`` if there's an error.

You can also delete all of your pushes (**be careful**):

.. code-block:: python

    await pb.async_delete_pushes()


Pushing to specific devices
^^^^^^^^^^^^^^^^^^^^^^^^^^^

So far all our pushes went to all connected devices, but there's a way to limit that.

First we need to get hold of some devices.

.. code-block:: python

    # Get all devices that the current user has access to.
    devices = await pb.async_get_devices()
    print(devices)
    # [Device('Motorola Moto G'), Device('N7'), Device('Chrome')]

    # Or retrieve a device by its name. Returns None if not found.
    motog = await pb.async_get_device(nickname='Motorola Moto G')


We can pass the device to push methods:

.. code-block:: python

    push = await pb.async_push_note("Hello world!", "We're using the api.", device=motog)

Creating new devices
^^^^^^^^^^^^^^^^^^^^

Creating a new device is easy too, you only need to specify a name for it.
Though you can also specify manufacturer, model and icon too.

.. code-block:: python

    coffee = await pb.async_new_device("MyCoffeePotGadget")
    # or
    motog = await pb.async_new_device("MotoG", manufacturer="Motorola", model="G", icon="android")


Now you can use it like any other device.

Editing devices
^^^^^^^^^^^^^^^

You can change the nickname, the manufacturer, model and icon of the device.  The new ``Device``
object is returned.

.. code-block:: python

    coffee = await pb.async_new_device("MyCoffeePotGadget")
    coffee2 = await pb.async_edit_device(coffee, manufacturer="Me!")

Deleting devices
^^^^^^^^^^^^^^^^

Of course, you can also delete devices, even those not added by your code.

.. code-block:: python

    await pb.async_remove_device(coffee)


Channels
^^^^^^^^

You can also send pushes to channels. First, create a channel on the Pushbullet
website (also make sure to subscribe to that channel). All channels which
belong to the current user can be retrieved as follows:

.. code-block:: python

    # Get all channels created by the current user
    channels = await pb.async_get_channels()
    print(channels)
    # [Channel('My Channel' 'channel_identifier')]

    # Or retrieve a channel by its name. Returns None if not found.
    mychannel = await pb.async_get_channel('My Channel')

Then you can send a push to all subscribers of this channel like so:

.. code-block:: python

    push = await pb.async_push_note("Hello Channel!", channel=mychannel)


Contacts
^^^^^^^^

Contacts, which are known as "Chats" in Pushbullet's terminilogy, work just like devices:

.. code-block:: python


    # Get all chats that the current user has access to.
    chats = await pb.async_get_chats()
    print(chats)
        # [Chat('Pushbullet Team' < pushbullet - team @ pushbullet.com >:
        # {'active': True,
        #  'created': 1484549777.2763588,
        #  'modified': 1484549777.276366,
        #  'muted': None,
        #  'with': {'email': 'pushbullet-team@pushbullet.com',
        #           'email_normalized': 'pushbullet-team@pushbullet.com',
        #           'iden': 'ujzob6qgcYm',
        #           'image_url': 'https://static.pushbullet.com/google-user/4308fcd45302c1dde28c5d86d7654da31bd32e70e9c28cac4a29d7f35c193e51',
        #           'name': 'Pushbullet Team',
        #           'type': 'user'}})]

    # How to access properties
    print("Active:", chats[0].active)
    print("Email:", chats[0].with_email)

    # Or retrieve a chat by its email. Returns None if not found.
    peter = await pb.async_get_chat('peter@gmail.com')


Now we can use the chat objects like we did with `pb` or with the devices.:

.. code-block:: python

    push = await pb.async_push_note("Hello world!", "We're using the api.", chat=peter)


Adding new chats
^^^^^^^^^^^^^^^^

.. code-block:: python

    bob = await pb.async_new_chat("Bob", "bob@gmail.com")


Sending SMS messages
^^^^^^^^^^^^^^^^^^^^

The author (Robert Harder) does not have any Android devices, so he has not
been able to test the ``asyncio`` versions of the sms functions.  In theory
they should work. :-/

.. code-block:: python

    motog = await pb.async_get_device(nickname='Motorola Moto G')
    push = await pb.async_push_sms(motog, "+3615555678", "Wowza!")

Sending Ephemerals
^^^^^^^^^^^^^^^^^^

The Pushbullet service has ephemeral messages that are not stored and are used
for, wait for it, ephemeral or transient messaging such as the universal clipboard
functionality.  You can send these messages as well.

.. code-block:: python

    msg = {"body": "something I copied", "type": "clip"}
    await pb.async_push_ephemeral(msg)

    msg = {"foobar": "Some control message you use for your IoT devices."}
    await pb.async_push_ephemerals(msg)


End-To-End encryption
^^^^^^^^^^^^^^^^^^^^^

The End-to-End notes are from the original ``Pushbullet`` project.

You activate end-to-end encryption by specifying your encryption key during the construction of the ``Pushbullet`` instance:

.. code-block:: python

    from pushbullet import Pushbullet

    pb = Pushbullet(api_key, "My secret password")

When specified, all sent SMS will be encrypted. Note that the use of end-to-end encryption requires the ``cryptography`` package. Since end-to-end encryption is only supported for SMS at the moment, the ``cryptography`` library is not specified as a dependency of ``pushbullet.py`` and should be installed seperatly by running ``pip install cryptography``.

Note that Pushbullet supportes End-To-End encryption only in SMS, notification mirroring and universal copy & paste. Your pushes will not be end-to-end encrypted.


Error checking
^^^^^^^^^^^^^^

If the Pushbullet api returns an error code an __
``InvalidKeyError`` or a ``PushbulletError`` is raised. The first __
two are both subclasses of ``PushbulletError``

The `pushbullet api documetation <https://www.pushbullet.com/api>`__
contains a list of possible status codes.

Listening for Pushes
^^^^^^^^^^^^^^^^^^^^

To listen for pushes, use the ``LiveStreamListener`` class in an ``async for`` loop:

.. code-block:: python

    async def _run():
        async with AsyncPushbullet(api_key) as pb:
            async with LiveStreamListener(pb) as pl:
                print("Awaiting pushes...")
                async for push in pl:
                    print("Got a push:", push)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run())


TODO
----

-  More tests. Write them all.

License
-------

MIT license. See LICENSE for full text.
