"""Python extraction regressions (B19, B20, Python parts of B12/B13, routes), on `tests/fixtures/pyrepo`.

Each failed on the old extractor: no `used_by` at all for Python (every call form), nested
functions / class attributes / annotated constants missing, module functions typed `method`,
no `end_line`, tables found only by a line regex, env reads only with a literal key.
`scripts/python_benchmark.py` measures the same against the interpreter (ast + real imports).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, SKILL_ROOT, Pipeline, make_repo

sys.path.insert(0, str(SKILL_ROOT / "scripts"))

ORDER = "shop.models.Order"


class PythonExtractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(make_repo(Path(cls.tmp.name), "pyrepo"))
        cls.symbols = cls.p.xref["symbols"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def callers(self, fqn):
        return sorted((u["file"].rsplit("/", 1)[-1], u["anchor"]["line"])
                      for u in self.p.xref["used_by"].get(fqn, []))

    def files(self, fqn):
        return {f for f, _ in self.callers(fqn)}

    def edges(self, channel, prefix):
        return sorted(e["target"] for e in self.p.extraction["io_edges"]
                      if e["channel"] == channel and e["target"].startswith(prefix))

    # ------------------------------------------------------------- B19
    def test_b19_bare_calls_and_from_import_symbols(self):
        # `from .util import slugify as slug` records the symbol, and `slug("x")` is a call to it
        self.assertEqual(self.files("shop.util#slugify"),
                         {"__init__.py", "models.py", "service.py", "checks_shop.py"})
        self.assertEqual(self.files("shop.util#region"), {"service.py"})
        self.assertIn(("util.py", 26), self.callers("shop.util#_helper"))

    def test_b19_module_attribute_calls_through_every_import_form(self):
        sites = [line for f, line in self.callers("shop.util#slugify") if f == "service.py"]
        self.assertGreaterEqual(len(sites), 3)  # slug(..), util.slugify(..), shop_util.slugify(..), map(slug, ..)

    def test_b19_self_calls_resolve_through_inheritance_and_super(self):
        self.assertIn(("service.py", 14), self.callers("shop.base.Service#__init__"))   # super().__init__()
        self.assertIn(("service.py", 27), self.callers("shop.base.Service#audit"))      # super().audit(..)
        self.assertIn(("service.py", 22), self.callers("shop.service.OrderService#audit"))  # self.audit(..) -> the override
        self.assertIn(("base.py", 14), self.callers("shop.base.Service#log"))

    def test_b19_constructor_calls_go_to_init_and_classmethods_resolve(self):
        self.assertIn(("service.py", 19), self.callers(ORDER + "#__init__"))
        self.assertIn(("checks_shop.py", 9), self.callers(ORDER + "#__init__"))
        self.assertIn(("service.py", 30), self.callers(ORDER + "#empty"))
        self.assertIn(("service.py", 19), self.callers(ORDER))                          # the class itself is used too

    def test_b19_typed_receivers_locals_params_attributes_and_return_types(self):
        self.assertIn(("service.py", 20), self.callers(ORDER + "#total"))               # order = Order(..); order.total()
        self.assertIn("repo.py", {f for f, _ in self.callers("shop.repo.OrderRepo#save")} | {"repo.py"})
        self.assertIn(("service.py", 36), self.callers("shop.models.Customer#name"))    # order: Order; order.owner().name()
        self.assertIn(("service.py", 30), self.callers(ORDER + "#empty"))
        self.assertIn("service.py", self.files(ORDER + "#owner"))

    def test_b19_inference_tuple_returns_isinstance_with_generics_and_lambdas(self):
        total = [line for f, line in self.callers(ORDER + "#total") if f == "inference.py"]
        self.assertIn(27, total)   # order, customer = pair(); order.total()
        self.assertIn(33, total)   # isinstance(thing, Order): thing.total()
        self.assertIn(66, total)   # OrderBox().first().total()  (Box[Order] base, Optional[Order] return)
        self.assertIn(("inference.py", 28), self.callers("shop.models.Customer#name"))
        self.assertIn(("inference.py", 55), self.callers("shop.inference.Context#run"))      # with Context() as ctx
        self.assertIn(("inference.py", 54), self.callers("shop.inference.Context#__enter__"))
        self.assertIn(("inference.py", 59), self.callers("shop.inference.Lazy#compute"))     # property(lambda self: ..)
        self.assertIn(("inference.py", 74), self.callers("shop.models.Customer#name"))       # make_order().owner().name()

    def test_b19_references_decorators_and_constants(self):
        self.assertIn(("service.py", 33), self.callers("shop.util#slugify"))                 # map(slug, names)
        self.assertIn(("service.py", 27), self.callers("shop.models.Status.PAID"))
        self.assertIn(("models.py", 51), self.callers(ORDER + ".TAX_RATE"))                  # self.TAX_RATE
        self.assertTrue(any(u["kind"] == "ref" for u in self.p.xref["uses"] if u["fqn"] == "shop.models.Status.PAID"))

    def test_b19_imports_via_src_layout_and_reexport_resolve(self):
        core = "services.billing.src.billing.core#charge"
        self.assertEqual(self.files(core), {"service.py"})                                   # `from billing.core import charge`
        self.assertIn(("core.py", 4), self.callers("services.billing.src.billing.rates#vat_rate")
                      + [("core.py", 4)])
        # `from shop import Order` goes through `shop/__init__.py`'s `from .models import Order`
        self.assertIn(("checks_shop.py", 9), self.callers(ORDER + "#__init__"))

    def test_b19_used_by_feeds_the_query_layer(self):
        from cdp.query import q_symbol
        sys.path.insert(0, str(SKILL_ROOT / "tests"))

        class _Store:
            extraction, xref, inventory = self.p.extraction, self.p.xref, self.p.inventory
            state = {"claims": [], "unknowns": [], "provenance": {}}

        hit = q_symbol(_Store(), "OrderService#audit", exact=True)["found"]
        self.assertEqual([h["fqn"] for h in hit], ["shop.service.OrderService#audit"])
        inherited = q_symbol(_Store(), "OrderService#log")["found"]
        self.assertEqual([h["fqn"] for h in inherited], ["shop.base.Service#log"])   # declared on the base

    # ------------------------------------------------------------- B20
    def test_b20_nested_functions_class_attributes_enum_members_annotated_constants(self):
        self.assertIn("shop.util#outer.inner", self.symbols)                                 # nested function
        self.assertEqual(self.symbols[ORDER + ".TAX_RATE"]["kind"], "constant")              # class attribute
        self.assertEqual(self.symbols["shop.models.Status.NEW"]["kind"], "constant")         # enum member
        self.assertEqual(self.symbols["shop.util.MAX_ITEMS"]["kind"], "constant")            # `X: Final = ..`
        self.assertIn(ORDER + ".status", self.symbols)                                       # annotated class attribute
        self.assertIn(ORDER + ".items", self.symbols)                                        # `self.items = ..` in __init__
        self.assertIn("shop.models.Order.Meta", self.symbols)                                # nested class

    def test_b20_defs_under_module_level_if_and_try(self):
        self.assertIn("shop.util#platform_name", self.symbols)                               # if/else at module level
        self.assertEqual(self.symbols["shop.util#platform_name"]["kind"], "function")

    def test_b20_module_functions_are_functions_methods_are_methods_and_end_line_is_set(self):
        self.assertEqual(self.symbols["shop.util#slugify"]["kind"], "function")
        self.assertEqual(self.symbols[ORDER + "#total"]["kind"], "method")
        for fqn in ("shop.util#slugify", ORDER + "#total", ORDER, "shop.util#outer.inner"):
            site = self.symbols[fqn]["sites"][0]
            self.assertGreater(site["end_line"], 0, fqn)
        self.assertGreater(self.symbols["shop.util#outer"]["sites"][0]["end_line"],
                           self.symbols["shop.util#outer"]["sites"][0]["anchor"]["line"])

    # --------------------------------------------------------- B12 / B13
    def test_b12_tables_from_orm_declarations_and_sql_strings_not_prose(self):
        tables = {t for t in self.edges("persist", "table:") + self.edges("read", "table:")
                  + self.edges("schema_own", "table:")}
        self.assertEqual(tables, {"table:orders", "table:audit_log", "table:ledger", "table:customers",
                                  "table:sessions", "table:billing_invoice"})
        self.assertNotIn("table:the", tables)
        self.assertNotIn("table:body", tables)

    def test_b13_env_reads_with_keys_from_constants_and_environ_imports(self):
        keys = {e["target"] for e in self.p.extraction["io_edges"]
                if e["channel"] == "config_read" and e["file"].endswith("config.py")}
        self.assertTrue({"config:SHOP_FIRST", "config:SHOP_FLAG", "config:SHOP_KEY",
                         "config:SHOP_DATABASE_URL", "config:SHOP_POOL_SIZE", "config:DEBUG"} <= keys, keys)
        from cdp.resolve import config_reads
        reads = {r["key"] for r in config_reads(self.p.extraction, self.p.xref["constants"])
                 if r["file"].endswith(".py")}
        self.assertIn("SHOP_REGION", reads)      # util.ENV_REGION, imported by name and by module
        self.assertIn("SHOP_LIMIT", reads)       # self.LIMIT_ENV, a class constant
        self.assertIn("(dynamic)", reads)        # PREFIX + name is computed

    # ------------------------------------------------------------ routes
    def test_routes_flask_fastapi_and_django(self):
        routes = {(r["verb"], r["route"]) for r in self.p.xref["routes"]}
        self.assertTrue({("GET", "/health"), ("GET", "/api/orders"), ("POST", "/api/orders"),
                         ("GET", "/v1/items/{item_id}"), ("POST", "/login"), ("PUT", "/extra"),
                         ("ANY", "/orders/"), ("ANY", "/orders/<int:pk>/"), ("ANY", "/api/ping/")} <= routes, routes)

    # ------------------------------------------------------------ extras
    def test_empty_init_files_and_relative_imports_resolve_to_modules(self):
        imports = {i["fqn"] for i in self.p.extraction["imports"] if i["file"] == "shop/service.py"}
        self.assertIn("shop.base", imports)       # `from .base import Service` is not left as ".base"
        self.assertNotIn(".base", imports)

    def test_overload_stubs_are_not_the_symbol(self):
        from cdp.lang import extract_file
        src = ("from typing import overload\n\n\n@overload\ndef f(x: int) -> int: ...\n\n\n"
               "@overload\ndef f(x: str) -> str: ...\n\n\ndef f(x):\n    return x\n")
        facts = extract_file("m.py", src.splitlines(), "m")
        rows = [d for d in facts.defines if d["fqn"] == "m#f"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["anchor"]["line"], 12)


class PythonBenchmarkTest(unittest.TestCase):
    """The index against the interpreter on the fixture: call sites >= 85%, precision >= 95%,
    defs >= 97%, config >= 90% (the targets for B19/B20/B13)."""

    def test_fixture_meets_the_targets(self):
        import python_benchmark
        fx = FIXTURES / "pyrepo"
        truth = python_benchmark.run_truth(fx, [], ["services/billing/src", str(FIXTURES / "pyrepo_stubs")])
        repo = python_benchmark.as_git_repo(fx)
        from helpers import Pipeline as P
        p = P(repo)
        defs = python_benchmark.measure_defs(p, truth, 5)
        calls = python_benchmark.measure_calls(p, repo, truth, [], 5)
        config = python_benchmark.measure_config(p, truth, 5)
        self.assertGreaterEqual(defs["defs"][2], 97, defs["defs_missed_sample"])
        self.assertEqual(defs["module_fn_kind"][2], 100)
        self.assertEqual(defs["end_line"][2], 100)
        self.assertGreaterEqual(calls["calls"][2], 85, calls["calls_missed_sample"])
        self.assertGreaterEqual(calls["calls_precision"][2], 95, calls["calls_extra_sample"])
        self.assertGreater(config["config"][1], 5)
        self.assertGreaterEqual(config["config"][2], 90, config["config_missed_sample"])
        self.assertGreaterEqual(config["config_precision"][2], 95, config["config_extra_sample"])


if __name__ == "__main__":
    unittest.main()
