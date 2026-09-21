# Know About — MCP Server (`mcp_server/`)

- Exactly 3 tools by design (`cdp_query`/`cdp_scan`/`cdp_status`), not a wider
  surface — the whole point is token-at-rest cost; a reference MCP server
  with 13 tools costs ~49k tokens permanently in a live session, this one
  measures at ~650.
- The SDK-facing half (`mcp.server.Server` wiring) is written against the
  documented shape but has never been run against a real `mcp` install in
  this environment — isolated to one function so the rest is fully testable
  without the dependency present.
- Query logic lives once, in `query.dispatch`, reused by both `cmd_query` and
  the MCP tools — never duplicated.
