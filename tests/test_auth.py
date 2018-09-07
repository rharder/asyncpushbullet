import os

import pytest
import asyncpushbullet

API_KEY = os.environ["PUSHBULLET_API_KEY"]

def test_auth_fail():
    with pytest.raises(asyncpushbullet.InvalidKeyError) as exinfo:
        pb = asyncpushbullet.Pushbullet("faultykey")
        # pb.session  # Triggers a connection
        pb.verify_key()


def test_auth_success():
    pb = asyncpushbullet.Pushbullet(API_KEY)
    _ = pb.get_user()
    assert pb._user_info["name"] == os.environ.get("PUSHBULLET_NAME", "Pushbullet Tester")
