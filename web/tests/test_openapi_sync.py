"""`web/openapi.json` is generated from the live app (`npm run generate` in web/client);
a stale copy hands the typed client a contract the server no longer has. `state_dir` is
echo-only (`resolve_state_dir`): the schema must say so on every endpoint that takes it."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from web.api.app import STATE_DIR_DESCRIPTION, app

OPENAPI = Path(__file__).resolve().parents[1] / "openapi.json"


class OpenApiSyncTest(unittest.TestCase):
    def test_committed_schema_matches_the_live_app(self) -> None:
        committed = json.loads(OPENAPI.read_text(encoding="utf-8"))
        self.assertEqual(committed, app.openapi(),
                         "web/openapi.json is stale: run `npm run generate` in web/client")

    def test_every_state_dir_parameter_says_it_is_an_echo(self) -> None:
        params = [p for path in json.loads(OPENAPI.read_text())["paths"].values()
                  for op in path.values() for p in op.get("parameters", []) if p["name"] == "state_dir"]
        self.assertTrue(params)
        for p in params:
            self.assertEqual(p.get("description"), STATE_DIR_DESCRIPTION)


if __name__ == "__main__":
    unittest.main()
