#!/usr/bin/env python

from pushbullet import Pushbullet

__author__ = "Robert Harder"
__email__ = "rob@iharder.net"

API_KEY = ""  # YOUR API KEY


def main():
    pb = Pushbullet(API_KEY)

    title = "Greetings"
    body = "Welcome to accessing Pushbullet with Python"
    pb.push_note(title, body)


if __name__ == "__main__":
    main()
