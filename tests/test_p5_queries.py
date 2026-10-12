"""P5 query semantics (H2, H3, H4, H9, B5): one scanned temp repo, queried the way a user does."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import have_git
from repo_layouts import Cdp, new_repo, pom

SQL = """CREATE TABLE server (id BIGINT PRIMARY KEY);
CREATE TABLE server_log (id BIGINT PRIMARY KEY);
CREATE TABLE server_hint (id BIGINT PRIMARY KEY);
CREATE TABLE pool_servers (id BIGINT PRIMARY KEY);
"""
SERVICE = """package com.acme.svc;

import com.acme.events.StatusChanged;
import com.acme.model.ServerRepo;
import com.google.common.eventbus.EventBus;

public class ServerService {
    private ServerRepo repo;
    private EventBus bus;
    public static final String MAGIC_HEADER = "X-Magic-Header";

    public int register(String name) {
        repo.findById(1L);
        bus.post(new StatusChanged(1L));
        return store(name);
    }

    int store(String name) {
        return name.length();
    }
}
"""
RESOURCE = """package com.acme.web;

import com.acme.svc.ServerService;
import javax.ws.rs.GET;
import javax.ws.rs.Path;

@Path("/v1/servers")
public class ServerResource {
    private final ServerService service = new ServerService();

    @GET
    public int list() {
        return service.register("a");
    }
}
"""
ENTITY = """package com.acme.model;

import javax.persistence.Entity;
import javax.persistence.Table;

@Entity
@Table(name = "server_log")
public class ServerEntity {
    private long id;
}
"""
REPO = """package com.acme.model;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ServerRepo extends JpaRepository<ServerEntity, Long> {
}
"""
EVENT = """package com.acme.events;

public class StatusChanged {
    public StatusChanged(long id) {
    }
}
"""
SUBSCRIBER = """package com.acme.sub;

import com.acme.events.StatusChanged;
import com.acme.model.ServerRepo;
import com.google.common.eventbus.Subscribe;

public class ServerSubscriber {
    private ServerRepo repo;

    @Subscribe
    public void onStatus(StatusChanged event) {
        repo.findById(1L);
    }
}
"""
KEYS = """package com.acme.svc;

public final class Keys {
    public static final String HOME = "pool.home";
    public static final String WAIT = HOME + ".wait";
    public static final String ENV = Names.PREFIX + "_ENV";
}
"""
NAMES = """package com.acme.svc;

public final class Names {
    public static final String PREFIX = "POOL";
}
"""
SETTINGS = """package com.acme.svc;

import static com.acme.svc.Keys.WAIT;

public class Settings {
    private static final String LOCAL = "pool.local";

    public String size() {
        return System.getenv("POOL_SIZE");
    }

    public String home() {
        return System.getProperty(Keys.HOME, "/tmp");
    }

    public String mode() {
        return System.getenv().getOrDefault("POOL_MODE",
            "test");
    }

    public long timeout() {
        return Long.getLong(LOCAL, 5L) + Long.getLong(WAIT, 1L);
    }

    public String envName() {
        return System.getenv(Keys.ENV);
    }

    public String other(String name) {
        return System.getenv(name);
    }

    public String again() {
        return System.getProperty(Keys.HOME);
    }
}
"""
CONFIG_YML = """server:
  applicationContextPath: /unified-store/svc
  applicationConnectors:
  - type: http
    bindHost: ${DW_APP_HOST:-0.0.0.0}
    port: ${DW_APP_PORT:-8070}
  - type: https
    port: 8443
  adminConnectors:
    - type: http
      port: 8071
logging:
  level: INFO
"""
TEST = """package com.acme.svc;

class ServerServiceTest {
    void registers() {
        new ServerService().register("t");
    }
}
"""


def build(tmp) -> "tuple":
    repo = new_repo(tmp, "p5")
    repo.write("pom.xml", pom("svc"))
    repo.write("src/main/resources/db/migration/V1__init.sql", SQL)
    repo.write("src/main/java/com/acme/svc/ServerService.java", SERVICE)
    repo.write("src/main/java/com/acme/web/ServerResource.java", RESOURCE)
    repo.write("src/main/java/com/acme/model/ServerEntity.java", ENTITY)
    repo.write("src/main/java/com/acme/model/ServerRepo.java", REPO)
    repo.write("src/main/java/com/acme/events/StatusChanged.java", EVENT)
    repo.write("src/main/java/com/acme/sub/ServerSubscriber.java", SUBSCRIBER)
    repo.write("src/main/java/com/acme/svc/Keys.java", KEYS)
    repo.write("src/main/java/com/acme/svc/Names.java", NAMES)
    repo.write("src/main/java/com/acme/svc/Settings.java", SETTINGS)
    repo.write("src/main/resources/config.yml", CONFIG_YML)
    repo.write("src/test/java/com/acme/svc/ServerServiceTest.java", TEST)
    repo.commit("initial")
    return repo


@unittest.skipUnless(have_git(), "needs git")
class P5QueryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = build(cls.tmp.name)
        cls.cdp = Cdp(cls.tmp.name, cls.repo.path)
        cls.cdp.scan()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def q(self, *args):
        import json
        return json.loads(self.cdp.run("query", *args, "--json", check=False).stdout)

    def test_h4_table_exact_returns_one_table_and_states_the_mode(self):
        loose = self.q("table", "server")
        self.assertEqual(loose["match"], "substring")
        self.assertGreaterEqual(loose["count"], 3)
        exact = self.q("table", "server", "--exact")
        self.assertEqual((exact["match"], exact["count"]), ("exact", 1))
        self.assertEqual(exact["tables"][0]["table"], "server")
        text = self.cdp.run("query", "table", "server").stdout
        self.assertIn("substring match", text)

    def test_h4_file_and_routes_state_their_mode_and_take_exact(self):
        loose = self.q("file", "ServerService")
        self.assertEqual(loose["match"], "substring")
        self.assertEqual(len(loose["found"]), 2)  # ServerService.java and ServerServiceTest.java
        exact = self.q("file", "ServerService.java", "--exact")
        self.assertEqual([f["path"] for f in exact["found"]],
                         ["src/main/java/com/acme/svc/ServerService.java"])
        self.assertEqual(self.q("routes", "/v1")["match"], "substring")
        self.assertEqual(self.q("routes", "/v1", "--exact")["count"], 0)
        self.assertEqual(self.q("routes", "/unified-store/svc/v1/servers", "--exact")["count"], 1)
        self.assertIn("route path or verb", self.cdp.run("query", "routes", "/v1").stdout)

    def test_h2_paths_match_any_node_on_the_path(self):
        end = self.q("paths", "--from", "ServerResource")
        self.assertGreaterEqual(end["count"], 1, end)
        mid = self.q("paths", "--from", "ServerService#register")
        self.assertGreaterEqual(mid["count"], 1, mid)
        self.assertIn("any node", mid["match"])
        through = self.q("paths", "--from", "ServerService", "--to", "ServerEntity")
        self.assertGreaterEqual(through["count"], 1, through)
        # order matters: nothing runs from the entity back to the resource
        self.assertEqual(self.q("paths", "--from", "ServerEntity", "--to", "ServerResource")["count"], 0)
        self.assertGreaterEqual(self.q("paths", "--to", "ServerService")["count"], 1)

    def test_b5_search_finds_a_constant_by_value_and_states_its_limit(self):
        hit = self.q("search", "X-Magic-Header")
        self.assertEqual(hit["counts"]["constants"], 1, hit)
        self.assertIn("MAGIC_HEADER", hit["constants"][0])
        miss = self.q("search", "zzz-not-there")
        self.assertIn("source text", miss["not_searched"])
        text = self.cdp.run("query", "search", "zzz-not-there", check=False).stdout
        self.assertIn("Not searched: source text of files that are not source-role", text)

    def test_h3_exclude_role_filters_used_by_and_rejects_unknown_roles(self):
        full = self.q("symbol", "ServerService#register")["found"][0]
        self.assertTrue(any("src/test" in u["at"] for u in full["used_by"]), full["used_by"])
        kept = self.q("symbol", "ServerService#register", "--exclude-role", "test")["found"][0]
        self.assertEqual(kept["used_by_count"], full["used_by_count"] - 1)
        self.assertFalse(any("src/test" in u["at"] for u in kept["used_by"]))
        bad = self.cdp.run("query", "symbol", "register", "--exclude-role", "bogusrole", check=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("unknown role", bad.stdout + bad.stderr)

    def test_b16_trace_reaches_the_event_subscriber(self):
        trace = self.q("trace", "/v1/servers")
        files = {f["file"]: f["why"] for f in trace["files"]}
        sub = "src/main/java/com/acme/sub/ServerSubscriber.java"
        self.assertIn(sub, files, sorted(files))
        self.assertIn("--event-->", files[sub])
        # and the subscriber is a path source of its own, ending at the table it writes
        paths = self.q("paths", "--from", "ServerSubscriber")
        self.assertTrue(any(p["hops"][-1]["to"].startswith("table:") for p in paths["paths"]), paths["paths"])
        # a `post` on something that is not an EventBus is not an event
        ev = [e for e in self.cdp.artifacts(["extract"])["extract"]["io_edges"] if e["target"].startswith("event:")]
        self.assertEqual(sorted((e["channel"], e["target"]) for e in ev),
                         [("event_publish", "event:com.acme.events.StatusChanged"),
                          ("event_subscribe", "event:com.acme.events.StatusChanged")])

    def test_b13_java_config_reads_are_indexed_with_resolved_keys(self):
        reads = {r["key"]: r for r in self.cfg_reads()}
        for key in ("POOL_SIZE", "pool.home", "POOL_MODE", "pool.local", "pool.home.wait", "POOL_ENV"):
            self.assertIn(key, reads, sorted(reads))
        self.assertIn("(dynamic)", reads)  # `System.getenv(name)`
        # a key spelled through another file's constants is resolved recursively
        self.assertEqual(reads["POOL_ENV"]["symbolic"], "${Keys.ENV}")
        # `getOrDefault` wraps across lines: the read is cited at the call, not lost
        self.assertTrue(reads["POOL_MODE"]["anchor"]["line"] in (16, 17, 18))

    def cfg_reads(self):
        from cdp.resolve import config_reads
        art = self.cdp.artifacts(["extract", "xref"])
        return [r for r in config_reads(art["extract"], art["xref"]["constants"])
                if r["file"].endswith("Settings.java")]

    def test_b13_yaml_lists_nest_and_env_placeholders_declare_config(self):
        keys = {r["fqn"][7:]: r.get("value") for r in self.cdp.artifacts(["extract"])["extract"]["defines"]
                if r["kind"] == "config_key" and r["fqn"].startswith("config:")}
        self.assertEqual(keys["server.applicationConnectors[0].port"], "${DW_APP_PORT:-8070}")
        self.assertEqual(keys["server.applicationConnectors[1].port"], "8443")
        self.assertEqual(keys["server.adminConnectors[0].port"], "8071")
        self.assertNotIn("server.port", keys)
        self.assertEqual(keys["DW_APP_PORT"], "8070")
        self.assertEqual(keys["DW_APP_HOST"], "0.0.0.0")

    def test_b21_config_shows_every_read_site_or_counts_the_elided(self):
        one = self.q("config", "pool.home", "--exact")["keys"][0]
        self.assertEqual(one["read_count"], 2)
        self.assertEqual(len(one["read"]), 2)               # both sites, not one
        self.assertEqual(self.q("config", "POOL_ENV")["keys"][0]["read_count"], 1)  # via constants
        tight = self.q("config", "pool.home", "--exact", "--budget", "2")
        self.assertEqual(tight["keys"][0]["key"], "pool.home")
        self.assertEqual(len(tight["keys"][0]["read"]), 1)
        self.assertEqual(tight["sites_elided"], 1)           # the missing site is counted
        self.assertEqual(tight["elided"], 1)

    def test_h1_default_budget_spends_on_citations_before_key_names(self):
        many = self.q("config", "--budget", "12")
        self.assertGreater(many["keys_elided"], 0)
        shown = many["keys"]
        self.assertTrue(shown)
        self.assertTrue(all(k["read"] or k["declared"] for k in shown), shown)
        self.assertEqual(shown[0]["key"], "pool.home")       # most-read first
        self.assertIn("elided_keys", many)
        full = self.q("config")
        self.assertEqual(full["keys_elided"], 0)

    def test_b15_routes_carry_the_context_path_and_exact_match(self):
        routes = self.q("routes")["routes"]
        self.assertEqual([r["route"] for r in routes], ["/unified-store/svc/v1/servers"])

    def test_h4_symbol_exact_and_config_exact(self):
        loose = self.q("symbol", "register")
        exact = self.q("symbol", "register", "--exact")
        self.assertEqual(exact["match"], "exact")
        self.assertEqual({f["fqn"].rsplit("#", 1)[-1] for f in exact["found"]}, {"register"})
        self.assertEqual(loose["match"], "substring")

    def test_h4_exact_is_rejected_where_it_does_not_apply(self):
        proc = self.cdp.run("query", "stats", "--exact", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("exact", proc.stdout + proc.stderr)

    def test_h4_mcp_tool_takes_exact(self):
        from mcp_server import tools
        import os
        old = os.environ.get("CDP_HOME")
        os.environ["CDP_HOME"] = str(self.cdp.home)
        try:
            out = tools.cdp_query(str(self.repo.path), "table", "server", exact=True)
        finally:
            if old is None:
                del os.environ["CDP_HOME"]
            else:
                os.environ["CDP_HOME"] = old
        self.assertEqual(out["count"], 1)


@unittest.skipUnless(have_git(), "needs git")
class DiffFilesAndSymbolsTest(unittest.TestCase):
    def test_h9_diff_reports_changed_files_and_symbols(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp)
            cdp = Cdp(tmp, repo.path)
            cdp.scan()
            old = repo.head()
            svc = "src/main/java/com/acme/svc/ServerService.java"
            repo.write(svc, repo.read(svc).replace("    int store(", "    int extra() {\n        return 2;\n    }\n\n    int store(")
                       .replace("        repo.findById(1L);\n", "        repo.findById(1L);\n        repo.findById(2L);\n"))
            repo.write("src/main/java/com/acme/web/ServerResource.java",
                       repo.read("src/main/java/com/acme/web/ServerResource.java").replace('"a"', '"abc"'))
            repo.write("src/main/resources/db/migration/V2__more.sql", "CREATE TABLE extra_t (id INT);\n")
            new = repo.commit("edit three files")
            cdp.scan()
            out = json.loads(cdp.run("diff", "--old-sha", old, "--new-sha", new, "--json").stdout)
            self.assertEqual(out["files"]["added"], ["src/main/resources/db/migration/V2__more.sql"])
            self.assertEqual(sorted(out["files"]["changed"]),
                             ["src/main/java/com/acme/svc/ServerService.java",
                              "src/main/java/com/acme/web/ServerResource.java"])
            self.assertIn("com.acme.svc.ServerService#extra", out["symbols"]["added"])
            self.assertIn("com.acme.svc.ServerService#register", out["symbols"]["changed"])
            text = cdp.run("diff", "--old-sha", old, "--new-sha", new).stdout
            self.assertIn("2 file(s) changed, 1 added", text)
            self.assertIn("+ com.acme.svc.ServerService#extra", text)


class PlaceholderTest(unittest.TestCase):
    def test_b15_constant_values_resolve_recursively_and_cycles_stay_unresolved(self):
        from cdp.resolve import expand_placeholders

        def c(value, line=1):
            return {"unambiguous": True, "value": value,
                    "candidates": [{"anchor": {"file": "A.java", "line": line}}]}

        table = {"Api.ROOT": c("/v1", 1), "Api.SERVERS": c("${Api.ROOT}/servers", 2),
                 "Loop.A": c("${Loop.B}"), "Loop.B": c("${Loop.A}")}
        text, anchors, missing = expand_placeholders("${Api.SERVERS}/{id}", table)
        self.assertEqual((text, missing), ("/v1/servers/{id}", []))
        self.assertEqual([a["line"] for a in anchors], [2, 1])
        text, _, missing = expand_placeholders("${Loop.A}/x", table)
        self.assertEqual(missing, ["Loop.A"])
        self.assertIn("${", text)


@unittest.skipUnless(have_git(), "needs git")
class OversizedFileGroupTest(unittest.TestCase):
    def test_b17_loose_files_over_the_limit_are_flagged(self):
        from cdp.inventory import build_inventory
        from cdp.partition import partition
        with tempfile.TemporaryDirectory() as tmp:
            repo = new_repo(tmp, "wide")
            repo.write("pom.xml", pom("wide"))
            for i in range(6):
                repo.write("src/main/java/com/acme/F%d.java" % i, "package com.acme;\npublic class F%d {}\n" % i)
            repo.write("src/main/java/com/acme/sub/G.java", "package com.acme.sub;\npublic class G {}\n")
            repo.commit("wide")
            part = partition(build_inventory(repo.path), max_files=3, max_loc=10000)
            groups = [s for s in part["scopes"] if s["node"].endswith("/(files)")]
            self.assertTrue(groups)
            big = [s for s in groups if s["file_count"] > 3]
            self.assertTrue(big, [(s["node"], s["file_count"]) for s in part["scopes"]])
            self.assertTrue(all(s["oversized"] for s in big))
            self.assertEqual(part["totals"]["oversized"], sum(1 for s in part["scopes"] if s["oversized"]))


if __name__ == "__main__":
    unittest.main()
