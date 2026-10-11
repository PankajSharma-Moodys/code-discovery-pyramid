"""Small helpers shared by the shop modules."""

import os
from typing import Final

MAX_ITEMS: Final = 10
DEFAULT_CURRENCY = "EUR"
ENV_REGION = "SHOP_REGION"
_registry = {}


def slugify(text):
    return text.lower().replace(" ", "-")


def region():
    return os.environ.get(ENV_REGION, "eu")


def _helper(value):
    return value


def outer():
    def inner(value):
        return _helper(value)

    return inner(1)


try:
    import ujson as json
except ImportError:
    import json


if os.name == "nt":

    def platform_name():
        return "windows"

else:

    def platform_name():
        return "posix"
