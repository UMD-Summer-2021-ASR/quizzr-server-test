import random
import string
from http import HTTPStatus
from secrets import token_urlsafe
from typing import Union


def generate_audio_id(nbytes=32):
    return token_urlsafe(nbytes)


def generate_uid(length=32):
    return ''.join([random.choice(string.ascii_letters + string.digits) for i in range(length)])


def match_status(expected: Union[int, HTTPStatus], actual: Union[str, int, HTTPStatus]):
    return expected == actual or str(int(expected)) in actual
