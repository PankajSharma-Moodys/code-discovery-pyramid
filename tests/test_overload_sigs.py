"""Overloads get a signature id (`Owner#name(T1,T2)`, cdp/sigs.py) beside the shared name.

Before: every overload in a file showed the pooled calls of all of them in `symbol`, and the
dataflow graph merged them into one node. Each language below has overloads that call different
things, a caller resolved by argument count, one resolved by argument type, one that cannot be
told apart (kept as candidates), and a method that is not overloaded (no `sig` at all).
"""

from __future__ import annotations

import copy
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline

from cdp import dataflow, sigs
from cdp.query.lookup import q_symbol
from cdp.query.trace import _walk, q_paths, q_trace


def _repo(tmp: Path, files: dict) -> Path:
    for rel, text in files.items():
        f = tmp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp)}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(tmp)] + args, check=True, capture_output=True, env=env)
    return tmp


class _Store:
    """Enough of a query Store for `symbol`, `trace` and `paths`."""

    def __init__(self, p: Pipeline, extraction=None, xref=None) -> None:
        self.extraction = extraction or p.extraction
        self.xref = xref or p.xref
        self.inventory, self.graph, self.dataflow = p.inventory, p.graph, p.dataflow
        self.state = {"claims": [], "unknowns": [], "provenance": {}}
        self._cache: dict = {}


class Base(unittest.TestCase):
    FILES: dict = {}
    OWNER = ""          # the class with the overloads
    NAME = ""           # the overloaded method's simple name

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), cls.FILES))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def sig(self, types: str) -> str:
        return "%s#%s(%s)" % (self.OWNER, self.NAME, types)

    def define_sigs(self, name: str):
        return sorted(d.get("sig") for d in self.p.extraction["defines"] if d["fqn"] == name)

    def call(self, line: int, target: str = ""):
        target = target or "%s#%s" % (self.OWNER, self.NAME)
        rows = [u for u in self.p.xref["uses"] if u.get("kind") == "call" and u["fqn"] == target
                and u["anchor"]["line"] == line]
        self.assertEqual(len(rows), 1, (line, target))
        return rows[0]

    def body(self, store=None):
        found = q_symbol(store or _Store(self.p), "%s#%s" % (self.OWNER, self.NAME), exact=True)["found"]
        self.assertEqual(len(found), 1)
        return {b["at"].rsplit(":", 1)[-1]: (b.get("sig"), sorted(b.get("calls", []))) for b in found[0]["body"]}

    def call_edges(self, source: str):
        return {(e["target"], e["confidence"]) for e in self.p.dataflow["edges"]
                if e["source"] == source and e["channel"] == "call"}

    def old_store(self):
        """The same facts as a store scanned before signatures existed: no `sig`, `from_sig`, `argt`."""
        ex, xr = copy.deepcopy(self.p.extraction), copy.deepcopy(self.p.xref)
        for row in ex["defines"] + ex["uses"] + xr["uses"]:
            for k in ("sig", "from_sig", "argt", "sig_by", "sig_candidates"):
                row.pop(k, None)
        for entry in xr["symbols"].values():
            for site in entry["sites"]:
                site.pop("sig", None)
        return _Store(self.p, ex, xr)


JAVA = {
    "pom.xml": "<project><artifactId>m</artifactId></project>",
    "src/main/java/a/Repo.java": """package a;

public class Repo {
    public void put(String s) { }
    public void log(int n) { }
    public void flush() { }
    public void tag(String... xs) { }
    public void tag(int n) { }
}
""",
    "src/main/java/a/Svc.java": """package a;

import java.util.List;

public class Svc {
    private final Repo repo = new Repo();

    public void save(String name) {
        repo.put(name);
        save(name, 1);
    }

    public void save(String name, int n) {
        repo.log(n);
    }

    public void save(List<String> names, int n) {
        repo.flush();
    }

    public void run(String s, int k, List<String> xs, Object o) {
        save(s);
        save(s, k);
        save(xs, k);
        save(o, k);
        repo.tag("a", "b");
        audit();
    }

    void audit() { }
}
""",
}


class JavaOverloadTest(Base):
    FILES, OWNER, NAME = JAVA, "a.Svc", "save"

    def test_overloads_get_a_sig_and_others_do_not(self):
        self.assertEqual(self.define_sigs("a.Svc#save"),
                         [self.sig("List,int"), self.sig("String"), self.sig("String,int")])
        self.assertEqual(self.define_sigs("a.Svc#audit"), [None])     # not overloaded: its name is its id
        self.assertEqual(self.define_sigs("a.Repo#tag"), ["a.Repo#tag(String...)", "a.Repo#tag(int)"])
        self.assertEqual([d.get("arity") for d in self.p.extraction["defines"] if d.get("sig") == "a.Repo#tag(String...)"],
                         [[0, None]])

    def test_calls_carry_the_enclosing_overload(self):
        self.assertEqual(self.call(9, "a.Repo#put")["from_sig"], self.sig("String"))
        self.assertEqual(self.call(14, "a.Repo#log")["from_sig"], self.sig("String,int"))
        self.assertNotIn("from_sig", self.call(27, "a.Svc#audit"))           # `run` is not overloaded

    def test_callee_resolved_by_arity_type_or_kept_as_candidates(self):
        self.assertEqual((self.call(22)["sig"], self.call(22)["sig_by"]), (self.sig("String"), "arity"))
        self.assertEqual((self.call(23)["sig"], self.call(23)["sig_by"]), (self.sig("String,int"), "type"))
        self.assertEqual((self.call(24)["sig"], self.call(24)["sig_by"]), (self.sig("List,int"), "type"))
        amb = self.call(25)                                                  # `save(Object, int)`
        self.assertNotIn("sig", amb)
        self.assertEqual(amb["sig_candidates"], [self.sig("List,int"), self.sig("String,int")])
        self.assertEqual(self.call(26, "a.Repo#tag")["sig"], "a.Repo#tag(String...)")   # varargs, 2 args
        self.assertNotIn("sig", self.call(27, "a.Svc#audit"))

    def test_symbol_body_is_per_overload(self):
        self.assertEqual(self.body(), {
            "8": (self.sig("String"), ["Repo#put", "Svc#save"]),
            "13": (self.sig("String,int"), ["Repo#log"]),
            "17": (self.sig("List,int"), ["Repo#flush"]),
        })

    def test_store_scanned_before_sigs_splits_by_line(self):
        self.assertEqual(self.body(self.old_store()), {
            "8": (None, ["Repo#put", "Svc#save"]), "13": (None, ["Repo#log"]), "17": (None, ["Repo#flush"])})

    def test_graph_nodes_are_overloads(self):
        self.assertEqual(self.call_edges(self.sig("String")),
                         {("a.Repo#put", "high"), (self.sig("String,int"), "high")})
        self.assertEqual(self.call_edges(self.sig("List,int")), {("a.Repo#flush", "high")})
        run = self.call_edges("a.Svc#run")
        self.assertIn((self.sig("String"), "high"), run)
        self.assertNotIn(("a.Svc#save", "high"), run)          # never the merged name
        self.assertFalse(any(e["source"] == "a.Svc#save" for e in self.p.dataflow["edges"]))

    def test_trace_of_the_name_walks_every_overload(self):
        files = q_trace(_Store(self.p), "a.Svc#save")
        self.assertTrue(files["found"])
        # put, log, flush and `save(String,int)` -- an overload `save(String)` calls is a node of its own
        self.assertTrue(files["trail"].startswith("4 node(s) reachable"), files["trail"])


SCALA = {
    "build.sbt": 'name := "m"\n',
    "src/main/scala/a/Svc.scala": """package a

class Repo {
  def put(s: String): Unit = ()
  def log(n: Int): Unit = ()
  def flush(): Unit = ()
}

class Svc(repo: Repo) {
  def save(name: String): Unit = {
    repo.put(name)
    save(name, 1)
  }

  private def save(name: String, n: Int): Unit = {
    repo.log(n)
  }

  def save(names: List[String], n: Int, extra: String = "x"): Unit = {
    repo.flush()
  }

  def tag(xs: String*): Unit = ()
  def tag(n: Int): Unit = ()

  def run(s: String, k: Int, xs: List[String], o: Any): Unit = {
    save(s)
    save(s, k)
    save(xs, k)
    save(o, k)
    tag("a", "b")
  }
}

object Svc {
  def save(name: String): Unit = ()
}
""",
}


class ScalaOverloadTest(Base):
    FILES, OWNER, NAME = SCALA, "a.Svc", "save"

    def test_overloads_get_a_sig(self):
        self.assertEqual(self.define_sigs("a.Svc#save"), [
            self.sig("List,Int,String"), self.sig("String"), self.sig("String") + "@object", self.sig("String,Int")])
        self.assertEqual(self.define_sigs("a.Svc#run"), [None])
        self.assertEqual(self.define_sigs("a.Svc#tag"), ["a.Svc#tag(Int)", "a.Svc#tag(String...)"])
        rows = {d["sig"]: d.get("arity") for d in self.p.extraction["defines"] if d.get("sig")}
        self.assertEqual(rows[self.sig("List,Int,String")], [2, 3])      # a default lowers the minimum
        self.assertEqual(rows["a.Svc#tag(String...)"], [0, None])

    def test_calls_carry_the_enclosing_overload(self):
        self.assertEqual(self.call(11, "a.Repo#put")["from_sig"], self.sig("String"))
        self.assertEqual(self.call(16, "a.Repo#log")["from_sig"], self.sig("String,Int"))

    def test_callee_resolution(self):
        self.assertEqual(self.call(12)["sig"], self.sig("String,Int"))      # by type among 2-arg ones
        self.assertEqual(self.call(28)["sig"], self.sig("String,Int"))
        self.assertEqual(self.call(29)["sig"], self.sig("List,Int,String"))
        self.assertEqual(self.call(30)["sig_candidates"],                     # `o: Any`: not guessed
                         [self.sig("List,Int,String"), self.sig("String,Int")])
        # `save(s)`: the class's and the companion object's overload take the same argument
        self.assertEqual(self.call(27)["sig_candidates"], [self.sig("String"), self.sig("String") + "@object"])
        self.assertEqual(self.call(31, "a.Svc#tag")["sig"], "a.Svc#tag(String...)")

    def test_symbol_body_is_per_overload(self):
        body = self.body()
        self.assertEqual(body["10"], (self.sig("String"), ["Repo#put", "Svc#save"]))
        self.assertEqual(body["15"], (self.sig("String,Int"), ["Repo#log"]))
        self.assertEqual(body["19"], (self.sig("List,Int,String"), ["Repo#flush"]))

    def test_store_scanned_before_sigs_splits_by_line(self):
        body = self.body(self.old_store())
        self.assertEqual(body["15"], (None, ["Repo#log"]))
        self.assertEqual(body["19"], (None, ["Repo#flush"]))

    def test_ambiguous_callee_reaches_each_candidate_at_medium(self):
        run = self.call_edges("a.Svc#run")
        self.assertIn((self.sig("String"), "medium"), run)
        self.assertIn((self.sig("String") + "@object", "medium"), run)


CSHARP = {
    "App.csproj": '<Project Sdk="Microsoft.NET.Sdk"></Project>\n',
    "Svc.cs": """namespace A
{
    public class Repo
    {
        public void Put(string s) { }
        public void Log(int n) { }
        public void Flush() { }
    }

    public class Svc
    {
        private readonly Repo repo = new Repo();

        public Svc() { }
        public Svc(int size) : this() { }

        public void Save(string name)
        {
            repo.Put(name);
            Save(name, 1);
        }

        public void Save(string name, int n, bool flag = false)
        {
            repo.Log(n);
        }

        public void Save(int id, int n)
        {
            repo.Flush();
        }

        public void Tag(params string[] xs) { }
        public void Tag(long? n) { }

        public void Run(string s, int k)
        {
            Save(s);
            Save(s, k);
            Save(k, k);
            Save(Get(), k);
            var x = new Svc(3);
            Tag("a", "b");
        }

        public string Get() { return ""; }
    }
}
""",
}


class CSharpOverloadTest(Base):
    FILES, OWNER, NAME = CSHARP, "A.Svc", "Save"

    def test_overloads_get_a_sig(self):
        self.assertEqual(self.define_sigs("A.Svc#Save"),
                         [self.sig("int,int"), self.sig("string"), self.sig("string,int,bool")])
        self.assertEqual(self.define_sigs("A.Svc#<init>"), ["A.Svc#<init>()", "A.Svc#<init>(int)"])
        self.assertEqual(self.define_sigs("A.Svc#Tag"), ["A.Svc#Tag(long?)", "A.Svc#Tag(string...)"])
        self.assertEqual(self.define_sigs("A.Svc#Run"), [None])
        rows = {d["sig"]: d.get("arity") for d in self.p.extraction["defines"] if d.get("sig")}
        self.assertEqual(rows[self.sig("string,int,bool")], [2, 3])
        self.assertEqual(rows["A.Svc#Tag(string...)"], [0, None])

    def test_calls_carry_the_enclosing_overload(self):
        self.assertEqual(self.call(19, "A.Repo#Put")["from_sig"], self.sig("string"))
        self.assertEqual(self.call(15, "A.Svc#<init>")["from_sig"], "A.Svc#<init>(int)")
        self.assertEqual(self.call(15, "A.Svc#<init>")["sig"], "A.Svc#<init>()")       # `: this()`

    def test_callee_resolution(self):
        self.assertEqual((self.call(38)["sig"], self.call(38)["sig_by"]), (self.sig("string"), "arity"))
        self.assertEqual((self.call(39)["sig"], self.call(39)["sig_by"]), (self.sig("string,int,bool"), "type"))
        self.assertEqual((self.call(40)["sig"], self.call(40)["sig_by"]), (self.sig("int,int"), "type"))
        self.assertEqual(self.call(41)["sig_candidates"], [self.sig("int,int"), self.sig("string,int,bool")])
        self.assertEqual(self.call(42, "A.Svc#<init>")["sig"], "A.Svc#<init>(int)")
        self.assertEqual(self.call(43, "A.Svc#Tag")["sig"], "A.Svc#Tag(string...)")

    def test_symbol_body_is_per_overload(self):
        self.assertEqual(self.body(), {
            "17": (self.sig("string"), ["Repo#Put", "Svc#Save"]),
            "23": (self.sig("string,int,bool"), ["Repo#Log"]),
            "28": (self.sig("int,int"), ["Repo#Flush"]),
        })

    def test_store_scanned_before_sigs_splits_by_line(self):
        self.assertEqual(self.body(self.old_store()), {
            "17": (None, ["Repo#Put", "Svc#Save"]), "23": (None, ["Repo#Log"]), "28": (None, ["Repo#Flush"])})

    def test_paths_and_text_show_the_signature(self):
        from cdp.query.render import render
        text = render(q_symbol(_Store(self.p), "A.Svc#Save", exact=True))
        self.assertIn("Svc#Save(string,int,bool): calls Repo#Log", text)
        self.assertEqual(q_paths(_Store(self.p), frm="A.Svc#Save")["query"], "paths")


CTORS = {
    "pom.xml": "<project><artifactId>m</artifactId></project>",
    "src/main/java/a/Clock.java": "package a;\n\npublic class Clock {\n    public long now() { return 0; }\n    public void tick() { }\n}\n",
    "src/main/java/a/Job.java": """package a;

public class Job {
    private final long born = new Clock().now();
    private String name;

    public Job() {
        this("x");
    }

    public Job(String name) {
        new Clock().tick();
    }
}
""",
}


class FieldInitialiserTest(Base):
    """A field initialiser runs in every constructor but sits outside every constructor's lines."""
    FILES, OWNER, NAME = CTORS, "a.Job", "<init>"

    def test_field_initialiser_calls_are_listed_under_every_constructor(self):
        body = self.body()
        self.assertEqual(set(body), {"7", "11"})
        for at, (sig, calls) in body.items():
            self.assertIn("Clock#now", calls, at)
        self.assertIn("Clock#tick", body["11"][1])
        self.assertNotIn("Clock#tick", body["7"][1])          # a constructor's own calls stay its own


def _edge(a: str, b: str, channel: str = "call") -> dict:
    return {"source": a, "target": b, "channel": channel, "module": "m", "confidence": "high",
            "anchor": {"file": "f", "line": 1}}


class HopLimitTest(unittest.TestCase):
    """One overload calling another (`save(String)` -> `save(String,int)`) is not counted toward the hop limit."""
    ADJ = {"E#in": [_edge("E#in", "S#save(String)")],
           "S#save(String)": [_edge("S#save(String)", "S#save(String,int)")],
           "S#save(String,int)": [_edge("S#save(String,int)", "R#put")],
           "R#put": [_edge("R#put", "table:t", "persist")]}

    def test_paths_do_not_count_an_overload_calling_another(self):
        source = {"node": "E#in", "trigger": "GET /x", "channel": "http_in", "module": "m"}
        paths, _ = dataflow._trace([source], self.ADJ, 3)     # 4 edges, 3 counted
        self.assertEqual([len(p["hops"]) for p in paths], [4])
        self.assertEqual(dataflow._trace([source], self.ADJ, 2)[0], [])

    def test_trace_does_not_count_an_overload_calling_another(self):
        reached, cut = _walk("E#in", self.ADJ, 3)
        self.assertIn("table:t", reached)
        self.assertFalse(cut)
        reached, cut = _walk("E#in", self.ADJ, 2)
        self.assertNotIn("table:t", reached)
        self.assertTrue(cut)


class RuleTest(unittest.TestCase):
    def test_param_type_rule(self):
        self.assertEqual(sigs.param_type("java.util.Map<String, List<~T>>"), "java.util.Map")
        self.assertEqual(sigs.param_type("~T"), "T")
        self.assertEqual(sigs.param_type("String[]", varargs=True), "String...")
        self.assertEqual(sigs.param_type("Map<K, V>", generics=True), "Map<K,V>")

    def test_only_overloads_get_a_sig_and_collisions_are_kept_apart(self):
        got = sigs.overload_sigs([("A#f", [("List<X>", False)], ""), ("A#f", [("List<Y>", False)], ""),
                                  ("A#g", [], ""), ("A#g", [], "IEnumerable"), ("A#h", [], ""), ("A#h", [], ""),
                                  ("A#k", [("int", False)], "")])
        self.assertEqual(got, ["A#f(List<X>)", "A#f(List<Y>)", "A#g()", "A#g()@IEnumerable", "A#h()", "A#h()@2", None])

    def test_names_and_display(self):
        self.assertEqual(sigs.name_of("p.A#m(java.lang.String,int)"), "p.A#m")
        self.assertEqual(sigs.name_of("config:(dynamic)"), "config:(dynamic)")
        self.assertEqual(sigs.short("p.A#m(java.lang.String)"), "A#m(java.lang.String)")
        self.assertEqual(sigs.sig_types("p.A#m(Map<K,V>,int)@2"), ["Map<K,V>", "int"])

    def test_collision_rule(self):
        self.assertEqual(sigs.collision([{"sig": "A#f(int)"}, {"sig": "A#f(String)"}]), (False, 2))
        self.assertEqual(sigs.collision([{"sig": "A#h()"}, {"sig": "A#h()@2"}]), (True, 1))
        self.assertEqual(sigs.collision([{}, {}]), (True, None))            # a class in main and test
        self.assertEqual(sigs.collision([{"sig": "A#f(int)"}]), (False, None))

    def test_resolution_never_guesses(self):
        sites = [{"sig": "A#f(int)"}, {"sig": "A#f(String)"}, {"sig": "A#f(int,int)"}]
        self.assertEqual(sigs.resolve(sites, 2, None), ("A#f(int,int)", "arity", []))
        self.assertEqual(sigs.resolve(sites, 1, ["String"]), ("A#f(String)", "type", []))
        self.assertEqual(sigs.resolve(sites, 1, ["?"]), (None, None, ["A#f(String)", "A#f(int)"]))
        self.assertEqual(sigs.resolve(sites, None, None)[2], ["A#f(String)", "A#f(int)", "A#f(int,int)"])


if __name__ == "__main__":
    unittest.main()
