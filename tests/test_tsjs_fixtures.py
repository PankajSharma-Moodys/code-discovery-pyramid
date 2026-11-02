"""TS/JS tree-sitter rules against the model-written fixtures in tests/fixtures/tsjs (expected.json written before the
first run and frozen; see the sha256 in the commit message). Run: python3 -m pytest tests/test_tsjs_fixtures.py"""
import json
import os

import pytest

from cdp.lang.base import ExtractContext
from cdp.lang.web import WebExtractor

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "tsjs")
EXPECT = json.load(open(os.path.join(DIR, "expected.json")))


def facts(name):
    lines = open(os.path.join(DIR, name)).read().splitlines()
    stem = name.rsplit(".", 1)[0]
    return WebExtractor().extract(ExtractContext(path="fx/" + name, lines=lines, module=""))


def check(row, want):
    got = {"kind": row["kind"], "vis": row["visibility"], "line": row["anchor"]["line"], "ret": row.get("ret"),
           "ftype": row.get("ftype"), "value": row.get("value"), "supertypes": row.get("supertypes"),
           "params": [[p["name"], p.get("type")] for p in row["params"]] if "params" in row else None,
           "annotations": [a["name"] for a in row.get("annotations", [])] if "annotations" in row else None}
    return all(got[k] == v for k, v in want.items() if k != "fqn")


@pytest.fixture(autouse=True)
def _inproc(monkeypatch):
    monkeypatch.setenv("CDP_TS_INPROC", "1")
    monkeypatch.setenv("CDP_TS", "typescript,javascript")


@pytest.mark.parametrize("name", sorted(EXPECT))
def test_fixture(name):
    f, exp = facts(name), EXPECT[name]
    bad = []
    for w in exp.get("defines", []):
        rows = [r for r in f.defines if r["fqn"] == "fx/" + w["fqn"][3:] and True]
        if not any(check(r, w) for r in rows):
            bad.append(("define", w, [(r["anchor"]["line"], r["kind"], r["visibility"], r.get("ret"), r.get("ftype"),
                                       r.get("params"), r.get("supertypes"),
                                       [a["name"] for a in r.get("annotations", [])]) for r in rows]))
    for a in exp.get("absent", []):
        if any(r["fqn"] == a for r in f.defines):
            bad.append(("absent but present", a))
    for s, t, c in exp.get("edges", []):
        if not any(e["source"] == s and e["target"] == t and e["channel"] == c for e in f.io_edges):
            bad.append(("edge", [s, t, c], [(e["source"], e["target"], e["channel"]) for e in f.io_edges]))
    assert not bad, json.dumps(bad, indent=1)[:1800]
