#!/usr/bin/env python3
import os
import sys

from setuptools import setup

with open("./asyncpushbullet/__version__.py") as version_file:
    version = version_file.read().split("\"")[1]

if len(sys.argv) < 2:
    cmd = input("Command (test or publish): ")
    sys.argv.append(cmd)

if sys.argv[-1] == 'test':
    print("TEST")
    os.system('python setup.py register -r pypitest')
    os.system('python setup.py sdist upload -r pypitest')
    sys.exit()

if sys.argv[-1] == 'publish':
    print("PUBLISH")
    os.system('python setup.py register -r pypi')
    os.system('python setup.py sdist upload -r pypi')
    sys.exit()

install_reqs = [
    "requests",
    "python-magic",
    "aiohttp",
    "tqdm"#,
   # "pillow"
]


def read(fname):
    try:
        with open(os.path.join(os.path.dirname(__file__), fname)) as f:
            return f.read()
    except IOError:
        return ""


setup(
    name="asyncpushbullet",
    version=version,
    author="Robert Harder, Richard Borcsik",
    author_email="rob@iharder.net, borcsikrichard@gmail.com",
    description=("A synchronous and asyncio-based client for pushbullet.com"),
    license="MIT",
    keywords="push android pushbullet notification",
    url="https://github.com/rharder/asyncpushbullet",
    download_url="https://github.com/rharder/asyncpushbullet/tarball/" + version,
    packages=['asyncpushbullet'],
    long_description=read('readme.rst'),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Natural Language :: English",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities"
    ],
    install_requires=install_reqs
)
