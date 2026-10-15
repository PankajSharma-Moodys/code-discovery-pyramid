"""`query table` on JPA code: writes and reads through a Spring Data repository and through a custom
EntityManager query, each credited to the table its call or query names (not to the entity's `@Table`)."""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import main
from cdp.query import Store, dispatch

PKG = "src/main/java/com/acme/"
FILES = {
    PKG + "Order.java": "package com.acme;\n@Entity @Table(name = \"orders\")\npublic class Order {\n  Long id;\n"
        "  @OneToMany(cascade = CascadeType.ALL, mappedBy = \"order\")\n  private java.util.List<OrderLine> lines;\n"
        "  @ManyToOne\n  @JoinColumn(name = \"customer_id\")\n  private Customer customer;\n"
        "  public java.util.List<OrderLine> getLines() { return lines; }\n}\n",
    PKG + "OrderLine.java": "package com.acme;\n@Entity @Table(name = \"order_lines\")\npublic class OrderLine { Long id; }\n",
    PKG + "Customer.java": "package com.acme;\n@Entity @Table(name = \"customers\")\npublic class Customer { Long id; }\n",
    PKG + "Audit.java": "package com.acme;\n@Entity @Table(name = \"audit_log\")\npublic class Audit { Long id; }\n",
    PKG + "OrderRepository.java": "package com.acme;\n"
        "public interface OrderRepository extends JpaRepository<Order, Long> {\n"
        "  java.util.List<Order> findByStatus(String s);\n}\n",
    PKG + "OrderRepositoryExt.java": "package com.acme;\n@Repository\npublic class OrderRepositoryExt {\n"
        "  private final EntityManager entityManager;\n"
        "  public OrderRepositoryExt(EntityManager entityManager) { this.entityManager = entityManager; }\n"
        "  public Long countOpen() {\n"
        "    return (Long) entityManager.createQuery(\"select count(o) from Order o\").getSingleResult();\n  }\n"
        "  public java.util.List<Audit> lastAudits() {\n"
        "    return entityManager.createQuery(\"select a from Audit a\", Audit.class).getResultList();\n  }\n}\n",
    PKG + "OrderService.java": "package com.acme;\npublic class OrderService {\n"
        "  private final OrderRepository orderRepository;\n  private final OrderRepositoryExt orderRepositoryExt;\n"
        "  public OrderService(OrderRepository r, OrderRepositoryExt x) { this.orderRepository = r; this.orderRepositoryExt = x; }\n"
        "  public void place(Order o) {\n    orderRepository.save(o);\n  }\n"
        "  public java.util.List<Order> open() {\n    return orderRepository.findByStatus(\"OPEN\");\n  }\n"
        "  public Long openCount() {\n    return orderRepositoryExt.countOpen();\n  }\n"
        "  public java.util.List<Audit> audits() {\n    return orderRepositoryExt.lastAudits();\n  }\n"
        "  public int lineCount(Order o) {\n    return o.getLines().size();\n  }\n}\n",
}


class TableAccessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls.repo, cls.state = root / "repo", root / "state"
        for rel, text in FILES.items():
            (cls.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (cls.repo / rel).write_text(text)
        git = lambda *a: subprocess.run(["git", "-C", str(cls.repo), *a], check=True, capture_output=True)
        git("init", "-q"); git("add", "-A")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["scan", "--repo", str(cls.repo), "--state-dir", str(cls.state), "--quiet", "--no-docs"]) == 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def table(self, name):
        store = Store(self.state)
        try:
            return dispatch(store, "table", name, exact=True, view="detail", format="json")["tables"][0]
        finally:
            store.close()

    @staticmethod
    def lines(groups):
        return {(g["through"].rsplit(".", 1)[-1], int(s.rsplit(":", 1)[1])) for g in groups for s in g["sites"]}

    def test_orders_is_written_and_read_through_its_repository_and_its_custom_query(self):
        t = self.table("orders")
        self.assertEqual(self.lines(t["repository_writes"]), {("OrderRepository", 7)})
        self.assertEqual(self.lines(t["repository_reads"]), {("OrderRepository", 10), ("OrderRepositoryExt", 13)})

    def test_a_custom_query_is_credited_to_the_table_it_names_not_to_its_class(self):
        t = self.table("audit_log")
        self.assertEqual(self.lines(t["repository_reads"]), {("OrderRepositoryExt", 16)})
        self.assertNotIn(("OrderRepositoryExt", 16), self.lines(self.table("orders")["repository_reads"]))

    def test_a_lazy_cascading_collection_is_written_with_its_owner_and_read_where_its_getter_is_called(self):
        t = self.table("order_lines")
        self.assertIn("Order.lines (@OneToMany, LAZY, cascade", t["repository_writes"][0]["through"])
        self.assertEqual({line for _, line in self.lines(t["repository_writes"])}, {7})   # orderRepository.save(o)
        self.assertEqual({line for _, line in self.lines(t["repository_reads"])}, {19})   # o.getLines()

    def test_an_eager_to_one_is_read_with_every_owner_read_and_not_written_without_cascade(self):
        t = self.table("customers")
        self.assertEqual({line for _, line in self.lines(t["repository_reads"])}, {10, 13})  # the orders reads
        self.assertEqual(t["repository_writes"], [])
        self.assertIn("Order.customer (@ManyToOne, EAGER", t["repository_reads"][0]["through"])

    def test_the_list_row_counts_the_calls(self):
        store = Store(self.state)
        try:
            row = dispatch(store, "table", "orders", exact=True, view="list", format="text")["text"]
        finally:
            store.close()
        self.assertIn("read by 2 call(s) via OrderRepository, OrderRepositoryExt", row)


if __name__ == "__main__":
    unittest.main()
