"""Settings from the environment."""

import os
from os import environ, getenv

from django.conf import settings
from pydantic import BaseSettings

from . import util
from .util import ENV_REGION

KEY_NAME = "SHOP_KEY"
PREFIX = "SHOP_"


class Settings(BaseSettings):
    database_url: str = "sqlite://"
    pool_size: int = 5

    class Config:
        env_prefix = "SHOP_"


class Reader:
    LIMIT_ENV = "SHOP_LIMIT"

    def limit(self):
        return os.getenv(self.LIMIT_ENV)


def read(name):
    first = environ["SHOP_FIRST"]
    second = getenv(KEY_NAME)
    third = os.environ.get(util.ENV_REGION)
    fourth = environ.get(ENV_REGION, "x")
    fifth = os.getenv(PREFIX + name)
    has = "SHOP_FLAG" in os.environ
    debug = settings.DEBUG
    return first, second, third, fourth, fifth, has, debug
