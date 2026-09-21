# How To — MCP Server (`mcp_server/`)

```bash
pip install cdp[mcp]
python3 -m mcp_server.server        # stdio MCP server (create_server/main)
```

Tools exposed: `cdp_query`, `cdp_scan`, `cdp_status` — resolved from the same
`.cdp.toml`/registry/cwd chain a CLI invocation in that directory would use.
