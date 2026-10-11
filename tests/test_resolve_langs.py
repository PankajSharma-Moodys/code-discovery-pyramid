"""Same FQN declared in C#, Java and Python must not cross-resolve: each use resolves against
the declarations of its own language only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_java_resolution import inline_repo

FILES = {
    "pom.xml": "<project><artifactId>m</artifactId></project>",
    "java/src/main/java/acme/Svc.java":
        "package acme;\npublic class Svc {\n  public void Missing() {}\n  public void JavaOnly() {}\n}\n",
    "java/src/main/java/acme/JUser.java":
        "package acme;\npublic class JUser {\n  void f(Svc s) {\n    s.Run();\n    s.Missing();\n  }\n}\n",
    "cs/Svc.cs":
        "namespace acme;\npublic class Svc\n{\n    public void Run() {}\n}\n",
    "cs/CUser.cs":
        "namespace acme;\npublic class CUser\n{\n    void F(Svc s)\n    {\n        s.Run();\n"
        "        s.Missing();\n        s.JavaOnly();\n    }\n}\n",
    "acme.py": "class Svc:\n    def PyOnly(self):\n        pass\n",
    "pyuser.py": "from acme import Svc\n\n\ndef f(s: Svc):\n    s.Run()\n    s.PyOnly()\n    s.Missing()\n",
}


class CollidingFqnTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), FILES))
        cls.used = cls.p.xref["used_by"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def users(self, key):
        return {(u["file"].rsplit("/", 1)[-1], u["anchor"]["line"]) for u in self.used.get(key, [])}

    def test_csharp_calls_never_reach_java_only_members(self):
        self.assertEqual(set(), {u for u in self.users("acme.Svc#Missing") if u[0] == "CUser.cs"})
        self.assertEqual(set(), self.users("acme.Svc#JavaOnly"))

    def test_java_call_never_reaches_csharp_only_member(self):
        self.assertEqual(set(), {u for u in self.users("acme.Svc#Run") if u[0] == "JUser.java"})

    def test_python_calls_resolve_only_to_python_members(self):
        self.assertTrue({u for u in self.users("acme.Svc#PyOnly") if u[0] == "pyuser.py"})
        for key in ("acme.Svc#Run", "acme.Svc#Missing", "acme.Svc#JavaOnly"):
            self.assertEqual(set(), {u for u in self.users(key) if u[0] == "pyuser.py"}, key)
        self.assertEqual(set(), {u for u in self.users("acme.Svc#PyOnly") if u[0] != "pyuser.py"})

    def test_own_language_still_resolves(self):
        self.assertTrue({u for u in self.users("acme.Svc#Run") if u[0] == "CUser.cs"})
        self.assertTrue({u for u in self.users("acme.Svc#Missing") if u[0] == "JUser.java"})


if __name__ == "__main__":
    unittest.main()
