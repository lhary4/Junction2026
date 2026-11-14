# `agent_mcp` — External Buying Agent MCP Server

Exposes the five Valio Aimo buying-agent tools over MCP `stdio` using `MCPServer` (`mcp >= 2.3`).
In Step C1, all tools read from `contract/examples/` relative to `agent_mcp/server.py`, so the server runs cleanly from any working directory.

## Run standalone

```bash
/Users/colettejoulie/.local/bin/uv run --python 3.14 --with "mcp>=2.3" python /Users/colettejoulie/Desktop/Junction2026/agent_mcp/server.py
```

## MCP Client Configuration (`claude_desktop_config.json` / `mcp_config.json`)

- **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json` (Settings -> Developer -> Edit Config)
- **Antigravity:** `~/.gemini/config/mcp_config.json` (`...` -> MCP Servers)

```json
{
  "mcpServers": {
    "valio-aimo": {
      "command": "/Users/colettejoulie/.local/bin/uv",
      "args": [
        "run",
        "--python",
        "3.14",
        "--with",
        "mcp>=2.3",
        "python",
        "/Users/colettejoulie/Desktop/Junction2026/agent_mcp/server.py"
      ]
    }
  }
}
```

## Step C1 Live Agent Timings (14/11)

- **MCP server startup & handshake (`mcp-server-valio-aimo.log`):** `380 ms` (`initialize`), `3 ms` (`tools/list`). All 9 automated stdio tool round-trips pass in `< 1 s`.
- **Prompt tested:** `I need 1,000 litres of lactose-free milk by Monday.`
- **Client tested on Colette's laptop:** Claude Desktop chat could not run prompts on this account; tested via Antigravity MCP client instead:

| Round | Time from sentence to final answer | Notes |
|---|---|---|
| 1 | ~2 min (120 s) | Completed tool flow via Antigravity MCP |
| 2 | > 6 min (timed out / no response) | Hung (IDE agent context + large data files open in workspace) |
| 3 | Not run (already well above the 30 s gate) | Fails the `< 30 s` live-agent threshold on this client |

- **Takeaway for the 14:05 decision:** Server + config block work cleanly (`380 ms` handshake). Unless Claude Desktop Pro on Adrien/Léon's machine hits `< 30 s`, use the planned **scripted runner (`scenarios/run.py`)** fallback — especially given Junction's strict **<= 2:00** pitch video cap.
