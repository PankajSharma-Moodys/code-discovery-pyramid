"""Disk cache of worker results. Key = sha1(rules version, op, lang, bytes); the version covers every rule/engine/extender file."""
import glob
import hashlib
import json
import logging
import os

HERE = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("cdp.ts")


def _version():
    fs = sorted(glob.glob(HERE + "/rules/**/*", recursive=True)) + [HERE + "/extender.py", HERE + "/engine.py", HERE + "/baseline.py"]
    return hashlib.sha1(b"".join(open(f, "rb").read() for f in fs if os.path.isfile(f))).hexdigest()[:12]


VERSION = _version()


def _dir():
    d = os.path.join(os.environ.get("CDP_HOME", os.path.expanduser("~/.cdp")), "tscache")
    os.makedirs(d, exist_ok=True)
    return d


def key(op, lang, data):
    return hashlib.sha1((VERSION + op + lang + "\0").encode() + data).hexdigest()


def get(k):
    try:
        return json.load(open(os.path.join(_dir(), k + ".json")))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.warning("tscache entry %s unreadable (%s); recomputing", k, e)
        return None


def put(k, result):
    try:
        tmp = os.path.join(_dir(), "%s.%d.tmp" % (k, os.getpid()))
        json.dump(result, open(tmp, "w"))
        os.replace(tmp, os.path.join(_dir(), k + ".json"))
    except OSError as e:
        log.warning("tscache write failed: %s", e)
