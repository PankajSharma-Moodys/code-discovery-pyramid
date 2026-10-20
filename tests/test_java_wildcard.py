"""Java on-demand imports: a name the file does not import singly is bound in javac's order --
a class of the file's own package if one is declared, else the wildcard-import owner that declares it.
Never the guessed same-package class when none exists (PLAN.md M3 bug A: `import Utils.*` once
bound `Constants` to the non-existent `WfSmoke.Constants`)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline

POM = """<project><modelVersion>4.0.0</modelVersion><groupId>g</groupId>
<artifactId>qe</artifactId><version>1</version></project>
"""

FILES = {
    "Utils/Constants.java": """package Utils;

public enum Constants {
  WORKFLOW_URI("u"),
  TENANT("t");
  private final String v;
  Constants(String v) { this.v = v; }
  public String getConstant() { return v; }
}
""",
    "Utils/Helper.java": """package Utils;

public class Helper {
  public static String ping() { return "p"; }
}
""",
    "Utils/Shared.java": """package Utils;

public class Shared {
  public static String who() { return "utils"; }
}
""",
    "WfSmoke/Shared.java": """package WfSmoke;

public class Shared {
  public static String who() { return "smoke"; }
}
""",
    "WfSmoke/SmokeTest.java": """package WfSmoke;

import Utils.*;

public class SmokeTest {
  private Helper helper = new Helper();

  public String run() {
    String a = Constants.WORKFLOW_URI.getConstant();
    String b = Helper.ping();
    String c = Shared.who();
    return a + b + c + helper.toString();
  }
}
""",
}


class JavaWildcardImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        repo = Path(cls.tmp.name) / "qe"
        root = repo / "src" / "main" / "java"
        for rel, text in FILES.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        (repo / "pom.xml").write_text(POM)
        cls.p = Pipeline(repo)
        cls.targets = {u["fqn"] for u in cls.p.xref["uses"]
                       if u.get("kind") and u["from_file"].endswith("SmokeTest.java")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_binding_to_an_undeclared_same_package_class(self):
        for t in self.targets:
            owner = t.split("#", 1)[0]
            self.assertFalse(owner.startswith("WfSmoke.") and owner not in self.p.xref["symbols"], t)

    def test_wildcard_owner_receives_the_type_and_its_calls(self):
        self.assertIn("Utils.Constants", self.targets)
        self.assertIn("Utils.Constants#getConstant", self.targets)
        self.assertIn("Utils.Helper#ping", self.targets)
        self.assertIn("Utils.Helper", self.targets)      # the field's declared type

    def test_declared_same_package_class_wins_over_the_wildcard(self):
        self.assertIn("WfSmoke.Shared#who", self.targets)
        self.assertNotIn("Utils.Shared#who", self.targets)

    def test_used_by_counts_the_wildcard_owner(self):
        users = self.p.xref["used_by"].get("Utils.Constants#getConstant", [])
        self.assertEqual([u["file"].rsplit("/", 1)[-1] for u in users], ["SmokeTest.java"])


if __name__ == "__main__":
    unittest.main()
