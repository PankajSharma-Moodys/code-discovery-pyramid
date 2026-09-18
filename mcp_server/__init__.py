"""MCP server for CDP (Phase 9, 7.1).

Three tools, deliberately: `cdp_query`, `cdp_scan`, `cdp_status`. The
reference point is `phase_9_plan.md`'s own argument -- a 13-tool MCP server
measured at ~49.2k tokens permanently resident in a session, which a
token-reduction product must not cost. `schemas.py` names the three tools'
descriptions/JSON schemas with zero dependency on the real `mcp` SDK, so
`schemas.estimate_at_rest_tokens()` can be measured without it installed;
`tools.py` is the tool logic, also SDK-free; `server.py` is the thin layer
that hands both to the real `mcp` `Server` (`pip install cdp[mcp]`).

Lives outside `cdp/` core: this package may depend on the `mcp` SDK; `cdp/`
itself never imports it (enforced by `tests/test_core_purity.py`).
"""

from __future__ import annotations
