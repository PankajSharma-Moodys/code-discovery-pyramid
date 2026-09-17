"""`.cdp.toml` team-config parsing (`cdp/store/registry.py`)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cdp.store import registry


class TeamBackendTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)

    def _write_toml(self, text: str) -> None:
        (self.repo / ".cdp.toml").write_text(text, encoding="utf-8")

    def test_defaults_to_sqlite_with_no_config(self):
        self.assertEqual(registry.team_backend(self.repo), "sqlite")

    def test_reads_backend_key(self):
        self._write_toml('backend = "file"\n')
        self.assertEqual(registry.team_backend(self.repo), "file")

    def test_no_postgres_config_returns_none(self):
        self.assertIsNone(registry.team_postgres_config(self.repo))

    def test_reads_postgres_table(self):
        self._write_toml(
            'backend = "postgres"\n\n[postgres]\ndsn = "postgresql://x/y"\nschema = "team1"\n'
        )
        self.assertEqual(registry.team_backend(self.repo), "postgres")
        self.assertEqual(
            registry.team_postgres_config(self.repo), {"dsn": "postgresql://x/y", "schema": "team1"}
        )

    def test_postgres_table_schema_is_optional(self):
        self._write_toml('[postgres]\ndsn = "postgresql://x/y"\n')
        self.assertEqual(registry.team_postgres_config(self.repo), {"dsn": "postgresql://x/y", "schema": None})


if __name__ == "__main__":
    unittest.main()
