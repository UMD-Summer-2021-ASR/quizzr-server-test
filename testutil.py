from http import HTTPStatus
from secrets import token_urlsafe
from typing import Union

import bson


def generate_audio_id(nbytes=32):
    return token_urlsafe(nbytes)


def match_status(expected: Union[int, HTTPStatus], actual: Union[str, int, HTTPStatus]):
    return expected == actual or str(int(expected)) in actual
