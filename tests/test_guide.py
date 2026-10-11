"""The guide is one source; every surface is generated from it (E10/E7/E9/E8/H8).

Fails when a kind or command lacks What/How/Where, when SKILL.md or
docs/CDP_REFERENCE.md drift from `cdp/guide_*.py`, when a flag is undescribed,
or when a query parameter a kind ignores is accepted instead of rejected.
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, FIXTURES, make_repo  # noqa: F401  (sets sys.path)

from cdp import guide, helpdoc, hook as hook_mod, query as query_mod
from cdp.guide_commands import COMMANDS, RECIPES
from cdp.guide_kinds import APPLIES, FLOW, KINDS, PARAMS
from cdp.parser import build_parser


def _commands():
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)


def _all_options(parser, path=""):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                yield from _all_options(sub, (path + " " + name).strip())
        elif not isinstance(action, argparse._HelpAction):
            yield path, action


class EveryKindAndCommandHasWhatHowWhere(unittest.TestCase):
    def test_kinds_match_the_query_registry(self) -> None:
        self.assertEqual(set(KINDS), set(query_mod.QUERIES))
        self.assertEqual(len(KINDS), 14)

    def test_each_kind_has_the_three_parts_and_an_example(self) -> None:
        for kind in KINDS:
            parts = guide.kind_sections(kind)
            for part in guide.PARTS:
                self.assertTrue(parts[part].strip(), "%s lacks %s" % (kind, part))
            self.assertTrue(KINDS[kind]["examples"], kind)
            self.assertTrue(set(APPLIES[kind]) <= set(PARAMS), kind)
            self.assertTrue(all(e.startswith("query %s" % kind) for e in KINDS[kind]["examples"]), kind)

    def test_each_command_has_the_three_parts_and_an_example(self) -> None:
        self.assertEqual(set(COMMANDS), set(_commands()))
        for name, c in COMMANDS.items():
            for part in guide.PARTS:
                self.assertTrue(c[part].strip(), "%s lacks %s" % (name, part))
            self.assertTrue(c["examples"], name)

    def test_flow_table_names_every_kind(self) -> None:
        self.assertEqual({k for _, k in FLOW}, set(KINDS))

    def test_recipes_cover_the_demo_questions(self) -> None:
        names = {r["name"] for r in RECIPES}
        self.assertTrue({"who-calls", "blast-radius", "route-tables", "config-reads", "two-repos",
                         "refresh"} <= names)

    def test_every_flag_and_positional_is_described(self) -> None:
        bare = ["%s %s" % (p, a.option_strings[0] if a.option_strings else a.dest)
                for p, a in _all_options(build_parser()) if not (a.help or "").strip()]
        self.assertEqual(bare, [])
        surface = helpdoc.describe(build_parser())
        for command in surface["commands"]:
            self.assertTrue(all(o["help"] for o in command["options"]), command["name"])
            self.assertTrue(command["examples"], command["name"])
        link = [c for c in surface["commands"] if c["name"] == "link"][0]
        self.assertEqual({s["name"] for s in link["subcommands"]},
                         {"scan", "query", "prompts", "collect", "run", "refresh"})


class GeneratedSurfacesMatchTheSource(unittest.TestCase):
    def test_skill_md_is_generated_and_compact(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text()
        self.assertEqual(text, guide.skill_md(), "run python3 scripts/gen_guide.py")
        self.assertLessEqual(len(text.splitlines()), 100)
        for needle in ("trace", "cdp_query", "cdp_help", "/cdp <question>", "coverage"):
            self.assertIn(needle, text)
        for kind in KINDS:
            self.assertIn("`%s`" % kind, text)

    def test_reference_is_generated_and_complete(self) -> None:
        text = (SKILL_ROOT / "docs" / "CDP_REFERENCE.md").read_text()
        self.assertEqual(text, guide.reference_md(), "run python3 scripts/gen_guide.py")
        self.assertLessEqual(len(text.splitlines()), 800)
        for kind in KINDS:
            self.assertIn("### `%s`" % kind, text)
        for name in COMMANDS:
            self.assertIn("### `%s`" % name, text)

    def test_help_text_serves_every_topic_from_the_guide(self) -> None:
        for topic in list(KINDS) + list(COMMANDS) + ["recipes"]:
            text = helpdoc.help_text(topic)
            self.assertTrue(text.strip(), topic)
        for kind in KINDS:
            self.assertEqual(helpdoc.help_text(kind), guide.render_kind(kind))
        self.assertEqual(helpdoc.help_text("reference"), guide.reference_md())
        self.assertIn("WHAT", helpdoc.help_text("query"))

    def test_unknown_help_topic_is_an_error(self) -> None:
        from cdp.util import CdpError

        with self.assertRaises(CdpError):
            helpdoc.help_text("nonesuch")

    def test_help_json_carries_kinds_with_three_parts(self) -> None:
        surface = json.loads(json.dumps(helpdoc.describe(build_parser())))
        self.assertEqual({k["name"] for k in surface["kinds"]}, set(KINDS))
        for k in surface["kinds"]:
            self.assertTrue(k["what"] and k["how"] and k["where"] and k["examples"])

    def test_query_flags_are_all_in_the_parameter_table(self) -> None:
        query = _commands()["query"]
        flags = {a.option_strings[0] for a in query._actions if a.option_strings}
        documented = {f for f, _ in PARAMS.values()} | {"-h", "--help", "--json", "--repo", "--state-dir"}
        self.assertEqual(flags - documented, set())


class HookTextLeadsWithMcp(unittest.TestCase):
    def test_nudge_names_cdp_query_first_and_no_link_kind(self) -> None:
        text = hook_mod.nudge_text("a" * 40, "src/A.java", False)
        self.assertLess(text.index("cdp_query"), text.index("cdp query"))
        self.assertIn("trace", text)

    def test_session_start_text_leads_with_mcp_and_omits_link(self) -> None:
        src = inspect.getsource(hook_mod.session_start)
        ready = src[src.index("index for this repo is ready"):]
        self.assertIn("cdp_query", ready)
        self.assertIn("cdp_help", ready)
        self.assertNotIn("link", ready)
        self.assertNotIn("run.py", ready)

    def test_prompt_submit_text_has_no_link_kind(self) -> None:
        src = inspect.getsource(hook_mod.prompt_submit)
        self.assertNotRegex(src, r"kinds:[^)]*link")
        self.assertIn("cdp_query", src)


class RejectsParametersAKindIgnores(unittest.TestCase):
    """E8 / H8, at the shared `dispatch` the CLI and MCP both use."""

    @classmethod
    def setUpClass(cls) -> None:
        import tempfile
        from cdp.cli import main
        import contextlib
        import io

        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name), "orderrepo")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["scan", "--repo", str(cls.repo), "--quiet"]) == 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def _store(self):
        from cdp.session import open_store, paths_for

        return query_mod.Store(open_store(paths_for(str(self.repo))))

    def test_every_unused_parameter_is_rejected_for_every_kind(self) -> None:
        sample = {"term": "x", "budget": 5, "exclude_role": ["test"], "claim_kind": "naming",
                  "module": "m", "subject": "s", "frm": "a", "to": "b", "max_hops": 2}
        store = self._store()
        try:
            for kind in KINDS:
                for param, value in sample.items():
                    if param in APPLIES[kind]:
                        continue
                    with self.assertRaises(ValueError, msg="%s accepted %s" % (kind, param)):
                        query_mod.dispatch(store, kind, value if param == "term" else None, **(
                            {} if param == "term" else {param: value}))
        finally:
            store.close()

    def test_claims_term_and_a_different_kind_conflict(self) -> None:
        store = self._store()
        try:
            with self.assertRaises(ValueError):
                query_mod.dispatch(store, "claims", "config", claim_kind="entrypoint")
            query_mod.dispatch(store, "claims", "entrypoint", claim_kind="entrypoint")
        finally:
            store.close()

    def test_unknown_role_is_rejected(self) -> None:
        store = self._store()
        try:
            with self.assertRaises(ValueError):
                query_mod.dispatch(store, "symbol", "OrderService", exclude_role=["bogusrole"])
        finally:
            store.close()

    def test_unknown_terms_say_not_found_with_a_suggestion(self) -> None:
        store = self._store()
        try:
            hit = query_mod.dispatch(store, "symbol", "OrderServce")
            self.assertEqual(hit["not_found"]["term"], "OrderServce")
            self.assertIn("OrderService", hit["not_found"]["did_you_mean"])
            self.assertIn("orders", query_mod.dispatch(store, "table", "ordrs")["not_found"]["did_you_mean"])
            self.assertIn("not_found", query_mod.dispatch(store, "trace", "/nope"))
            self.assertNotIn("not_found", query_mod.dispatch(store, "symbol", "OrderService"))
            self.assertNotIn("not_found", query_mod.dispatch(store, "routes"))
        finally:
            store.close()

    def test_cli_exits_1_on_not_found_and_0_on_found(self) -> None:
        import contextlib
        import io
        from cdp.cli import main

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["query", "symbol", "OrderServce", "--repo", str(self.repo)])
        self.assertEqual(rc, 1)
        self.assertIn("did you mean: OrderService", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["query", "symbol", "OrderService", "--repo", str(self.repo)]), 0)


if __name__ == "__main__":
    unittest.main()
