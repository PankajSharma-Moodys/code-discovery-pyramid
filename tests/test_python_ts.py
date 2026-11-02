"""Python declarations from the shared tree-sitter layer (cdp/lang/python_ts.py, rules/python.scm)."""
import pytest

from cdp.lang.base import ExtractContext
from cdp.lang.python import PythonExtractor

SRC = '''import functools
from fastapi import APIRouter
from .base import Base

router = APIRouter()
LIMIT = 5
count: int = 0


class Model(Base, object, metaclass=Meta):
    __slots__ = ()
    name: str = "x"
    _hidden = 1
    __secret = 2

    @property
    def title(self, a: int, b=2, *args, c: str = "d", **kw) -> str:
        return ""

    @functools.lru_cache(maxsize=2)  # comment
    def cached(self):
        pass


@router.get("/x/{id}", response_model=Model, tags=["a", "b"])
async def get_x(id: int, /, q): pass


def outer():
    class Inner(Model): pass
    def helper(a): pass
    local = 1
'''


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("CDP_HOME", str(tmp_path))
    monkeypatch.setenv("CDP_TS_INPROC", "1")


def rows(src=SRC, path="pkg/m.py"):
    f = PythonExtractor().extract(ExtractContext(path=path, lines=src.splitlines(), module=""))
    return {d["fqn"]: d for d in f.defines}, f


def test_declarations_from_the_tool():
    r, _ = rows()
    assert r["pkg.m.Model"]["supertypes"] == ["pkg.base.Base"] and r["pkg.m.Model"]["end_line"] == 22
    assert r["pkg.m.LIMIT"]["kind"] == "constant" and r["pkg.m.count"]["kind"] == "field" and "pkg.m.local" not in r
    assert r["pkg.m.Model._hidden"]["visibility"] == "internal" and r["pkg.m.Model.__secret"]["visibility"] == "private"
    assert r["pkg.m#outer.helper"]["kind"] == "function" and r["pkg.m#outer#Inner"]["supertypes"] == ["pkg.m.Model"]
    assert [p["name"] for p in r["pkg.m.Model#title"]["params"]] == ["self", "a", "b", "args", "c", "kw"]
    assert r["pkg.m.Model#title"]["params"][1]["type"] == "int" and "type" not in r["pkg.m.Model#title"]["params"][2]


def test_decorator_name_args_fqn_and_comment():
    r, _ = rows()
    a = r["pkg.m.Model#cached"]["annotations"][0]
    assert a["name"] == "functools.lru_cache" and a["args"] == {"maxsize": 2} and a["text"] == "@functools.lru_cache(maxsize=2)"
    g = r["pkg.m#get_x"]["annotations"][0]
    assert g["fqn"] == "fastapi.APIRouter.get" and g["args"] == {"value": "/x/{id}", "response_model": {"ref": "Model"}, "tags": ["a", "b"]}
    assert r["pkg.m.Model#title"]["annotations"][0]["fqn"] == "builtins.property" and "args" not in r["pkg.m.Model#title"]["annotations"][0]


def test_resolver_encoding_stays():
    r, _ = rows()
    assert r["pkg.m.Model#title"]["ftype"] == "str" and "ret" not in r["pkg.m.Model#title"]      # a property carries ftype, as before
    assert r["pkg.m#get_x"].get("ret") is None and r["pkg.m.Model#cached"].get("ret") is None
    assert r["pkg.m.count"]["ftype"] == "int" and r["pkg.m.Model.name"]["ftype"] == "str"


def test_python2_file_still_gets_declarations():
    r, f = rows("class A(B):\n    def m(self, x):\n        print x\n")
    assert any(n.startswith("parse_error") for n in f.notes) and r["pkg.m.A"]["supertypes"] == ["B"] and r["pkg.m.A#m"]["params"][1]["name"] == "x"


def test_tool_off_keeps_flow_rows(monkeypatch):
    monkeypatch.setenv("CDP_TS", "off")
    r, _ = rows()
    assert "pkg.m.Model" in r and "supertypes" not in r["pkg.m.Model"] and "params" not in r["pkg.m#get_x"] and not r["pkg.m#get_x"].get("annotations")


EDGES = '''from flask_restx import Namespace, Resource
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as sa
from alembic import op

ns = Namespace("a")
db = SQLAlchemy()


@ns.route("/items")
class Items(Resource):
    def get(self): pass
    def post(self): pass


class Tag(db.Model):
    __tablename__ = "tags"
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(
        db.String(10))


class Loose:
    n = sa.Column(sa.Integer)


def upgrade():
    op.create_table("things", sa.Column("id", sa.Integer), sa.Column("x", sa.Text))
    y = sa.Column("y", sa.Text)
'''


def test_class_level_routes_and_column_sites():
    _, f = rows(EDGES)
    e = [(x["source"].rsplit(".", 1)[-1], x["target"], x["channel"], x["anchor"]["line"]) for x in f.io_edges
         if x["channel"] in ("http_in", "persist") and not x["target"].startswith("library:")]
    assert ("Items", "route:GET /items", "http_in", 10) in e and ("Items", "route:POST /items", "http_in", 10) in e
    assert ("Tag", "table:tags", "persist", 18) in e and ("Tag", "table:tags", "persist", 19) in e
    assert ("Loose", "entity:pkg.m.Loose", "persist", 24) in e
    assert ("m#upgrade", "table:things", "persist", 28) in e and ("m#upgrade", "table:(dynamic)", "persist", 29) in e
    assert len([x for x in e if x[1] == "table:things"]) == 1          # two Column( on one line are one site
