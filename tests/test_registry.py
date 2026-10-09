"""`.cdp.toml` team config (`cdp/store/registry.py`): only `exclude` is read;
the keys that moved to `CDP_HOME/config.toml` are rejected, not ignored."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cdp.store import registry
from cdp.util import CdpError


class TeamConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)

    def _write_toml(self, text: str) -> None:
        (self.repo / ".cdp.toml").write_text(text, encoding="utf-8")

    def test_no_file_is_fine(self):
        registry.check_team_config(self.repo)
        self.assertEqual(registry.team_excludes(self.repo), [])

    def test_exclude_is_read(self):
        self._write_toml('exclude = ["notes", "scratch"]\n')
        registry.check_team_config(self.repo)
        self.assertEqual(registry.team_excludes(self.repo), ["notes", "scratch"])

    def test_a_backend_key_is_rejected_with_a_pointer_to_the_machine_config(self):
        self._write_toml('backend = "postgres"\n')
        with self.assertRaises(CdpError) as ctx:
            registry.check_team_config(self.repo)
        message = str(ctx.exception)
        self.assertIn("backend", message)
        self.assertIn("config.toml", message)

    def test_store_and_postgres_keys_are_rejected_too(self):
        for text in ('store = "/shared/x"\n', '[postgres]\ndsn = "postgresql://x/y"\n'):
            self._write_toml(text)
            with self.assertRaises(CdpError):
                registry.check_team_config(self.repo)


if __name__ == "__main__":
    unittest.main()
