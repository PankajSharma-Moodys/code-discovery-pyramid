"""K1 (value conflicts against the index) and K2 (DTOs called persisted, test-only production claims)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

import repo_layouts as L
from repo_layouts import Cdp

CORE = "core/src/main/java/COM/Example/mini/core/"
DTO = CORE + "WidgetDto.java"
DTO_TEST = "core/src/test/java/COM/Example/mini/core/WidgetDtoTest.java"
ENTITY = CORE + "WidgetEntity.java"


def claim(cid, subject, file, line, anchor, statement, kind="data_model", **extra):
    return dict({"id": cid, "kind": kind, "subject": subject, "confidence": "high", "statement": statement,
                 "evidence": [{"file": file, "line": line, "anchor": anchor}]}, **extra)


@L.needs_git
class ClaimQualityTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.repo = L.Repo(make_repo(tmp, "minirepo"))
        self.repo.write(DTO, "package com.example.mini.core;\n\npublic class WidgetDto {\n    private String name;\n}\n")
        self.repo.write(DTO_TEST, "package com.example.mini.core;\n\npublic class WidgetDtoTest {\n"
                                  "    void writesWidget() {\n    }\n}\n")
        self.repo.commit("dto and test")
        self.cdp = Cdp(tmp, self.repo.path)
        self.cdp.scan()

    def collect(self, claims):
        backend, store = self.cdp.open()
        try:
            patch = {"schema_version": "1.0.0", "node": "root/core", "run_id": store.manifest["run_id"],
                     "status": "complete", "claims": claims, "unknowns": []}
            (backend._inbox_dir() / "root__core.json").write_text(json.dumps(patch))
        finally:
            backend.close()
        out = self.cdp.run("collect", check=False)
        backend, store = self.cdp.open()
        try:
            return out, {c["id"] for c in store.state["claims"]}
        finally:
            backend.close()

    def test_dto_called_persisted_is_rejected_and_the_entity_is_kept(self):
        dto = claim("t.dto", "com.example.mini.core.WidgetDto", DTO, 3, "public class WidgetDto {",
                    "WidgetDto is persisted to the widget database table.", kind="naming")
        ent = claim("t.entity", "com.example.mini.core.WidgetEntity", ENTITY, 8, '@Entity @Table(name = "widget")',
                    "WidgetEntity is persisted to the widget table.", kind="naming")
        out, ids = self.collect([dto, ent])
        self.assertIn("t.entity", ids)
        self.assertNotIn("t.dto", ids)
        self.assertIn("wire/DTO", out.stdout + out.stderr)

    def test_production_side_effect_cited_only_from_a_test_is_rejected(self):
        bad = claim("t.sidefx", "com.example.mini.core.writesWidget", DTO_TEST, 4, "void writesWidget() {",
                    "The service writes widgets to the database.", kind="side_effect")
        good = claim("t.entity", "com.example.mini.core.WidgetEntity", ENTITY, 8, '@Entity @Table(name = "widget")',
                     "WidgetEntity maps widgets.", kind="naming")
        out, ids = self.collect([bad, good])
        self.assertNotIn("t.sidefx", ids)
        self.assertIn("t.entity", ids)

    def test_conflicts_reports_a_different_table_name_against_the_index(self):
        subject = "entity:com.example.mini.core.WidgetEntity"
        self.cdp.inject_model_patch("root/core", [
            claim("t.table", subject, ENTITY, 8, '@Entity @Table(name = "widget")',
                  "The table name is server for this entity.", channel="persist")])
        backend, store = self.cdp.open()
        try:
            clashes = [c for c in store.state["conflicts"] if c.get("reason") == "value"]
        finally:
            backend.close()
        self.assertEqual(len(clashes), 1, store.state["conflicts"])
        values = {v for p in clashes[0]["positions"] for v in p["values"].values()}
        self.assertEqual(values, {"server", "widget"})

    def test_agreeing_table_name_is_not_a_conflict(self):
        subject = "entity:com.example.mini.core.WidgetEntity"
        self.cdp.inject_model_patch("root/core", [
            claim("t.table", subject, ENTITY, 8, '@Entity @Table(name = "widget")',
                  "Mapped with @Table(name=\"widget\").", channel="persist")])
        backend, store = self.cdp.open()
        try:
            self.assertEqual([c for c in store.state["conflicts"] if c.get("reason") == "value"], [])
        finally:
            backend.close()


if __name__ == "__main__":
    unittest.main()
