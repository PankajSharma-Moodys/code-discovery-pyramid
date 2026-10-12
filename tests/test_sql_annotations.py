"""ANNOTATIONS_PLAN P7: SQL in annotations -> `table:` / `entity:` edges (`sql_tables`, `emit.sql` rules)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import extraction_of, have_git
from repo_layouts import Cdp, new_repo, pom

from cdp import rules
from cdp.lang.base import ExtractContext
from cdp.lang.data import sql_tables
from cdp.lang.java import JavaExtractor


def edges(src: str, path: str = "a/C.java", *more):
    facts = [JavaExtractor().extract(ExtractContext(path, src.split("\n"), "a"))]
    facts += [JavaExtractor().extract(ExtractContext(p, s.split("\n"), "a")) for p, s in more]
    ex = extraction_of(*facts)
    return sorted((e["source"], e["target"], e["channel"], e["rule"]) for e in rules.all_edges(ex) if e.get("rule", "").startswith(("sql.", "jpa.")) and not e["rule"].startswith("jpa.entity"))


def tgt(src: str, *more) -> list:
    return [(t, c) for _s, t, c, _r in edges(src, "a/C.java", *more)]


class SqlTablesTest(unittest.TestCase):
    def test_reads_and_writes(self):
        self.assertEqual(sql_tables("SELECT * FROM server s JOIN pool_config p ON p.id = s.pid"),
                         [("server", "read"), ("pool_config", "read")])
        self.assertEqual(sql_tables("update server set a = 1 where id = ?"), [("server", "write")])
        self.assertEqual(sql_tables("DELETE FROM server WHERE id = :id"), [("server", "write")])
        self.assertEqual(sql_tables("insert into server (a) select a from other"),
                         [("server", "write"), ("other", "read")])
        self.assertEqual(sql_tables("MERGE INTO tgt t USING src s ON t.id = s.id WHEN MATCHED THEN UPDATE SET a = 1 "
                                    "WHEN NOT MATCHED THEN INSERT (a) VALUES (1)"), [("tgt", "write"), ("src", "read")])
        self.assertEqual(sql_tables("truncate table foo"), [("foo", "write")])

    def test_qualified_and_quoted_names(self):
        self.assertEqual(sql_tables("select * from dbo.server"), [("server", "read")])
        self.assertEqual(sql_tables("select * from [dbo].[server] s"), [("server", "read")])
        self.assertEqual(sql_tables('select * from "public"."pool config" c'), [("pool config", "read")])
        self.assertEqual(sql_tables("select * from `db`.`server`"), [("server", "read")])
        self.assertEqual(sql_tables("SELECT * FROM SERVER"), [("SERVER", "read")])      # case kept, keyword any case

    def test_comma_lists_and_subqueries(self):
        self.assertEqual(sql_tables("select * from a x, b y, (select 1 from c) z, d where x.i in (select i from e)"),
                         [("a", "read"), ("b", "read"), ("c", "read"), ("d", "read"), ("e", "read")])
        self.assertEqual(sql_tables("select a, b from t order by a, b"), [("t", "read")])
        self.assertEqual(sql_tables("select * from a join b using (id)"), [("a", "read"), ("b", "read")])

    def test_cte_names_are_not_tables(self):
        sql = "with recent as (select * from server), n(x) as (select 1 from recent) select * from n join pool p on 1=1"
        self.assertEqual(sql_tables(sql), [("server", "read"), ("pool", "read")])

    def test_placeholders(self):
        self.assertEqual(sql_tables("insert into ${schema}.server (a) values (:a)"), [("server", "write")])
        self.assertEqual(sql_tables("select * from ${table}"), [])
        self.assertEqual(sql_tables("select * from :table"), [])
        self.assertEqual(sql_tables("select * from pool_${env}_cfg, ?"), [])
        self.assertEqual(sql_tables("select * from server where a = ?1 and b::text = #{b}"), [("server", "read")])

    def test_comments_and_strings_are_not_sql(self):
        sql = "select 'x from fake join nope' as s /* join hidden */ from real -- delete from gone\n where a = ';'"
        self.assertEqual(sql_tables(sql), [("real", "read")])
        self.assertEqual(sql_tables("select 'it''s from x' from t"), [("t", "read")])

    def test_not_tables(self):
        self.assertEqual(sql_tables("select extract(year from d) from t for update"), [("t", "read")])
        self.assertEqual(sql_tables("select 1 from dual"), [])
        self.assertEqual(sql_tables("select * from generate_series(1, 3) g, t"), [("t", "read")])
        self.assertEqual(sql_tables("select a from t where a is distinct from b"), [("t", "read")])
        self.assertEqual(sql_tables("insert into t (a) select a from u on duplicate key update a = 1, b = 2"),
                         [("t", "write"), ("u", "read")])

    def test_update_alias_resolves_to_its_table(self):
        self.assertEqual(sql_tables("update s set a = 1 from server s join cfg c on 1=1"),
                         [("server", "write"), ("server", "read"), ("cfg", "read")])
        self.assertEqual(sql_tables("delete s from server s where 1=1"), [("server", "write"), ("server", "read")])

    def test_jpql_entities(self):
        self.assertEqual(sql_tables("SELECT e FROM EServer e JOIN e.items i LEFT JOIN FETCH e.x WHERE e.a IN "
                                    "(SELECT o.a FROM Other o)", jpql=True), [("EServer", "read"), ("Other", "read")])
        self.assertEqual(sql_tables("UPDATE EServer e SET e.a = 1", jpql=True), [("EServer", "write")])
        self.assertEqual(sql_tables("DELETE FROM EServer e", jpql=True), [("EServer", "write")])
        self.assertEqual(sql_tables("select new com.x.Dto(e.a) from com.x.EServer e", jpql=True), [("EServer", "read")])


HEAD = "package a;\nimport org.springframework.data.jpa.repository.Query;\nimport org.springframework.data.jpa.repository.Modifying;\n"


class AnnotationRulesTest(unittest.TestCase):
    def test_native_delete_is_a_writer(self):
        src = HEAD + 'interface R {\n  @Modifying\n  @Query(value = "delete from dbo.server where id = ?1", nativeQuery = true)\n  void drop(long id);\n}\n'
        self.assertEqual(edges(src), [("a.R#drop", "table:server", "persist", "sql.spring_data.native")])

    def test_native_flag_selects_the_dialect(self):
        src = HEAD + 'interface R {\n  @Query(value = "select * from server", nativeQuery = false)\n  List<X> a();\n}\n'
        self.assertEqual(edges(src), [("a.R#a", "entity:server", "read", "sql.spring_data.jpql")])

    def test_jpql_select_is_a_reader_via_entity(self):
        src = HEAD + 'interface R {\n  @Query("select s from EServer s join s.pool p where s.x = :x")\n  List<X> a();\n}\n'
        self.assertEqual(edges(src), [("a.R#a", "entity:EServer", "read", "sql.spring_data.jpql")])

    def test_jpql_entity_with_a_named_table_also_yields_the_table(self):
        ent = ("a/EServer.java", "package a;\nimport javax.persistence.Entity;\nimport javax.persistence.Table;\n"
               '@Entity\n@Table(name = "server_tbl")\nclass EServer {}\n')
        src = HEAD + ('interface R {\n  @Query("select s from EServer s")\n  List<X> a();\n'
                      '  @Modifying\n  @Query("update EServer s set s.a = 1")\n  void u();\n'
                      '  @Query("select o from Unmapped o")\n  List<X> o();\n}\n')
        self.assertEqual(tgt(src, ent), [("entity:EServer", "read"), ("table:server_tbl", "read"),
                                         ("entity:Unmapped", "read"), ("table:server_tbl", "persist")])

    def test_placeholder_schema_and_text_block(self):
        src = HEAD + ('interface R {\n  @Query(nativeQuery = true, value = """\n      select s.id\n        from ${schema}.server s\n'
                      '        join pool_config pc on pc.id = s.cid\n      """)\n  List<X> a();\n}\n')
        self.assertEqual(tgt(src), [("table:pool_config", "read"), ("table:server", "read")])

    def test_concatenated_value(self):
        src = HEAD + ('interface R {\n  @Query(value = "update server " +\n      "set a = 1 where id in (select id from tmp)", nativeQuery = true)\n'
                      '  void u();\n}\n')
        self.assertEqual(tgt(src), [("table:server", "persist"), ("table:tmp", "read")])

    def test_comments_and_strings_do_not_make_edges(self):
        src = HEAD + ('interface R {\n  @Query(value = "select \'from fake\' as f /* join gone */ from real -- from nope\\n where 1=1", nativeQuery = true)\n'
                      '  void u();\n}\n// @Query("select * from commented")\n')
        self.assertEqual(tgt(src), [("table:real", "read")])

    def test_cte(self):
        src = HEAD + 'interface R {\n  @Query(value = "with x as (select * from server) select * from x", nativeQuery = true)\n  void u();\n}\n'
        self.assertEqual(tgt(src), [("table:server", "read")])

    def test_constant_reference_is_left_out(self):
        src = HEAD + 'interface R {\n  String Q = "select * from server";\n  @Query(value = Q, nativeQuery = true)\n  void u();\n}\n'
        self.assertEqual(tgt(src), [])          # `{"ref"}` constants are not resolved at rule time

    def test_named_queries(self):
        src = ('package a;\nimport javax.persistence.NamedQuery;\nimport javax.persistence.NamedNativeQuery;\n'
               '@NamedQuery(name = "A.all", query = "select e from EServer e")\n'
               '@NamedNativeQuery(name = "A.n", query = "update server set a = 1")\nclass EServer {}\n')
        self.assertEqual(edges(src), [("a.EServer", "entity:EServer", "read", "sql.jpa.named_query"),
                                      ("a.EServer", "table:server", "persist", "sql.jpa.named_native_query")])

    def test_jdbi_and_mybatis(self):
        src = ('package a;\nimport org.jdbi.v3.sqlobject.statement.SqlQuery;\nimport org.jdbi.v3.sqlobject.statement.SqlUpdate;\n'
               'import org.apache.ibatis.annotations.Select;\nimport org.apache.ibatis.annotations.Delete;\n'
               'interface D {\n  @SqlQuery("select * from server where id = :id") X a(long id);\n'
               '  @SqlUpdate("insert into pool_log (a) values (:a)") void b();\n'
               '  @Select({"select * from cfg c", "join pool p on p.id = c.pid"}) X c();\n'
               '  @Delete("delete from [dbo].[old]") void d();\n}\n')
        self.assertEqual([(s.rsplit("#", 1)[1], t, c) for s, t, c, _r in edges(src)],
                         [("a", "table:server", "read"), ("b", "table:pool_log", "persist"), ("c", "table:cfg", "read"),
                          ("c", "table:pool", "read"), ("d", "table:old", "persist")])

    def test_a_different_query_annotation_is_not_sql(self):
        src = ('package a;\nimport org.springframework.data.mongodb.repository.Query;\n'
               'interface R {\n  @Query("select * from server")\n  void u();\n}\n')
        self.assertEqual(tgt(src), [])


@unittest.skipUnless(have_git(), "needs git")
class TableQueryTest(unittest.TestCase):
    def test_q_table_shows_annotated_methods(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = new_repo(tmp, "p7")
            repo.write("pom.xml", pom("svc"))
            repo.write("src/main/java/com/acme/EServer.java",
                       "package com.acme;\nimport javax.persistence.Entity;\nimport javax.persistence.Table;\n"
                       '@Entity\n@Table(name = "server")\npublic class EServer {}\n')
            repo.write("src/main/java/com/acme/ServerRepo.java",
                       "package com.acme;\nimport org.springframework.data.jpa.repository.Query;\n"
                       "import org.springframework.data.jpa.repository.JpaRepository;\n"
                       "public interface ServerRepo extends JpaRepository<EServer, Long> {\n"
                       '  @Query(value = "delete from server where id = ?1", nativeQuery = true)\n  void purge(long id);\n'
                       '  @Query("select s from EServer s")\n  java.util.List<EServer> all();\n'
                       '  @Query(value = "select * from pool_cfg", nativeQuery = true)\n  java.util.List<Object> cfg();\n}\n')
            repo.commit("initial")
            cdp = Cdp(tmp, repo.path)
            cdp.scan()
            tables = {t["table"]: t for t in cdp.query_json("table")["tables"]}
            self.assertEqual(sorted(tables), ["pool_cfg", "server"])
            server = tables["server"]
            self.assertIn("com.acme.ServerRepo#purge", server["written_by"])
            self.assertIn("com.acme.ServerRepo#all", server["read_by"])
            self.assertIn("com.acme.ServerRepo#cfg", tables["pool_cfg"]["read_by"])
            purge = next(w for w in server["writers"] if w["fqn"] == "com.acme.ServerRepo#purge")
            self.assertTrue(purge["sites"][0].startswith("src/main/java/com/acme/ServerRepo.java:5"))


if __name__ == "__main__":
    unittest.main()
