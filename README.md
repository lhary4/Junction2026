# Junction2026: Trusted Trade Agents for Valio Aimo

How an outside buying agent can search, get a quote and order from a food-service wholesaler, with every order signed by the agent, by a human, or by nobody.

- `PLAN.md`: the idea, the architecture, the demo, the timeline.
- `team/README.md`: how each of us starts a session.
- `docs/contract.md`: the messages the pieces exchange.
- `TECH-CHOICES.md`: every technical choice, in plain words.

## Hosted demo

For the jury, the whole demo runs on a small server. Nothing to start on a laptop.

- **Page**: https://valio.adriencaillo.com/ (the kitchen order page, its chat and the three scenario buttons).
- **MCP server**, to add as a connector in claude.ai: `https://valio.adriencaillo.com/mcp-<token>`. The token is not in this repo, ask Adrien. Whoever has it can place sandbox orders.
- It runs in live mode (`VALIO_MODE=live`): real Valio prices and stock, on the real clock. The scenarios ask for a delivery on Thu 19 Nov, and Valio's order cut-off for that day is **Sun 15 Nov, 17:00 Helsinki time**. After it, live mode answers "late delivery" to the three buttons: see "Change the mode" below.
- The page is public and has no login: anyone with the link can press the buttons, sign an order and use the chat on our Gemini key. It is switched off after judging.

### How it is put together

One public address serves everything, so the browser sees the page and the services as one site.

| Address | Goes to | What it is |
|---|---|---|
| `/` | 127.0.0.1:8004 | the page and its files |
| `/assistant/...` | 127.0.0.1:8004 | the chat |
| `/driver/...` | 127.0.0.1:8003 | the demo driver |
| `/harness/...` | 127.0.0.1:8002 | the harness: policy, the chef's signature |
| `/mcp-<token>` | 127.0.0.1:8005, as `/mcp` | the MCP server |
| any other `/mcp...` | nothing | 404 |
| `/driver/agent/...`, `/harness/authorize` | nothing | 404: the agent's own routes and the route that judges and signs |
| `/docs`, `/redoc`, `/openapi.json`, also under `/driver` and `/harness` | nothing | 404: the API pages FastAPI generates |

The gateway (8001) is never public: only the harness, the driver and the MCP server call it, on the server itself.

The proxy also answers 404 to what no page calls (the last two rows): the MCP server and the driver reach those routes on the server itself, so a visitor cannot ask for a quote or an authorization without the page's buttons or the MCP address. The buttons still place sandbox orders, and the sandbox invoice account holds EUR 20,000: start again from an empty state before the jury (commands below).

- The four services and the MCP server run as the user `junction`, from `/opt/junction-2026/repo`, and only listen on 127.0.0.1. No port is open besides the web ones (80 and 443) the server already had.
- Caddy, the reverse proxy that was already on the server, does the HTTPS and the routing above: `deploy/Caddyfile.snippet`.
- Caddy runs in Docker and cannot reach the server's 127.0.0.1, so four small relays pass its connections on: `deploy/junction-bridge@.socket`.
- `deploy/junction-demo.service` runs `scripts/dev.py`, `deploy/junction-mcp.service` runs `agent_mcp/server.py --http valio.adriencaillo.com`. Both restart on their own if they stop.
- `.env` on the server holds the two API keys, `VALIO_MODE=live`, `MERCHANT_URL` and `HARNESS_URL` (local addresses) and `PUBLIC_ORIGIN=https://valio.adriencaillo.com`, the address the approval link sent to the chef starts with.

### Commands

On the server, as root (`ssh root@65.21.1.154`). `junction-demo` is the main switch: it starts and stops the MCP server and the relays with it.

```
systemctl status junction-demo junction-mcp     # is it running
journalctl -u junction-demo -f                  # what the four services print
systemctl restart junction-demo                 # restart everything, keeping orders and approvals
systemctl disable --now junction-demo           # switch everything off (after judging)
```

After every start or restart, read the catalog into memory, in the two services that use it, one after the other. Otherwise the first search and the first click on Spotlight each wait 5 to 10 seconds:

```
curl -s -o /dev/null 'http://127.0.0.1:8001/products/search?q=butter&limit=1'
curl -s -o /dev/null -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8004/recommend
```

Memory: in live mode the catalog takes about 500 MB in the gateway and 500 MB more in the page service (Spotlight reads it too), so 1.25 GB in all on a server that has 3.8 GB. `junction-demo` is slowed down above 1.5 GB and stopped above 1.8 GB, so that it can never starve the other things the server runs. `systemctl status junction-demo` shows the figure.

Start again from an empty state (what `scripts/dev.py --fresh` does), before a rehearsal or the jury:

```
systemctl stop junction-demo
runuser -u junction -- rm -rf /opt/junction-2026/repo/state/merchant /opt/junction-2026/repo/state/buyer
systemctl start junction-demo
```

Change the mode: edit `VALIO_MODE` in `/opt/junction-2026/repo/.env` (`live` or `replay`), then start again from an empty state as above. Replay serves the answers recorded on 14/11 with the clock frozen: the three buttons always end the same way, and the MCP server only knows the 157 recorded products.

Put a new version on the server. It has no access to GitHub, so the code is pushed to it from a laptop that has SSH access:

```
git push --receive-pack='runuser -u junction -- git-receive-pack' ssh://root@65.21.1.154/opt/junction-2026/repo origin/main:refs/heads/main
ssh root@65.21.1.154 "cd /opt/junction-2026/repo && runuser -u junction -- git switch main && runuser -u junction -- env HOME=/opt/junction-2026 /opt/junction-2026/.local/bin/uv sync --frozen && systemctl restart junction-demo"
```
