#!/usr/bin/env python3
import os
import shutil
import sys

from setuptools import setup
# You may need to pip install twine

with open("./asyncpushbullet/__version__.py") as version_file:
    version = version_file.read().split("\"")[1]

# version += "a2"
# sys.argv.append("install")

print(f"Version {version}")

if len(sys.argv) < 2:
    cmd = input("Command (build | test | publish | all ): ")
    sys.argv.append(cmd)

if sys.argv[-1] in ('build', 'all'):
    print("BUILD")
    for path in ("./build", "./dist", "./asyncpushbullet.egg-info"):
        try:
            print("Removing {} ...".format(path), end="", flush=True)
            shutil.rmtree(path)
        except:
            print("Could not remove {}".format(path), flush=True)
        else:
            print("Removed.")

    try:
        # os.system('python3 setup.py sdist bdist_wheel')
        os.system('python3 setup.py sdist')
    except:
        print("Do you need to pip install wheel?", file=sys.stderr)
        # os.system('python3 setup.py sdist bdist_wheel')
    # sys.exit()

if sys.argv[-1] in ('test', 'all'):
    print("TEST")
    try:
        os.system('twine upload -r pypitest dist/*')
    except:
        print("Do you need to pip install twine?", file=sys.stderr)
    # sys.exit()

if sys.argv[-1] in ('publish', 'all'):
    print("PUBLISH")
    try:
        os.system('twine upload -r pypi dist/*')
    except:
        print("Do you need to pip install twine?", file=sys.stderr)
    # sys.exit()

if sys.argv[-1] in ('build', 'test', 'publish', 'all'):
    sys.exit()

install_reqs = [
    "requests",
    "python-magic",
    "aiohttp",
    "tqdm",
    "appdirs"
    # , "pillow"
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
        # "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities"
    ],
    install_requires=install_reqs,
    extras_require={
        'GUI': ["pillow"]
    },
    entry_points={
        "console_scripts": ["pbpush=asyncpushbullet.command_line_push:main_pbpush",
                            "pbtransfer=asyncpushbullet.command_line_push:main_pbtransfer",
                            "pblisten=asyncpushbullet.command_line_listen:main"
                            ]
    }
)
