# Spikes: small scripts that proved a choice works

Not product code. They are here so the proof stays in the repo and so the real code can be lifted from them. Run from the repo root. `uv` downloads what each script needs, nothing is installed in the project.

## `ap2/`: real AP2 mandates on the Valio case

```
uv run --no-project --python 3.14 --with "ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56db72a6385bce3e5c1112b3a56ce60acb43" python spikes/ap2/ap2_valio_test.py
```

Expected last lines: `13/13 cases behave as expected`, then timings of 1 to 2 ms. The cases: an order inside the mandate is accepted; a tampered quote, a substitute outside the signed list, a wrong quantity, another merchant, a forged mandate, another agent's key, two replays, an expired mandate and an amount above the cap are refused.

`ap2_valio_test2.py` (same command, other file) shows the signed payment chain for the spend cap, and an order signed directly by the manager: accepted with the manager's key, refused with the agent's key.

## `stack/`: AP2, MCP and FastAPI in one project

```
uv run --no-project --python 3.14 --with "ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56db72a6385bce3e5c1112b3a56ce60acb43" --with "fastapi==0.162.7" --with "uvicorn==0.54.0" --with "mcp==2.3.0" python spikes/stack/run_test.py
```

It runs the MCP server over stdio in its own process (how Claude Desktop launches it), FastAPI in a second process reading what the first wrote, and MCP over HTTP inside the FastAPI process. It writes its state to `spikes/state/` (ignored by git).

Worth reading before writing the real thing:
- `core.py`: creating the keys and the open mandates, signing a quote, closing a mandate as the agent, signing as the human, verifying both chains. This becomes `trust/`.
- `mcp_server.py`: the smallest MCP server. In `mcp` 2.x the class is `MCPServer`, not `FastMCP`.
- `web.py`: mounting the MCP server inside a FastAPI app.

## `valio-data/`: where the demo numbers come from

`explore_demo_products.py` lists the lactose-free milks and the plant-based drinks with their live price, stock, cut-off, reliability, carbon footprint, allergens and labels. It needs the product file, the `.env` file, an output folder and a delivery date as arguments. Note: Valio's API answers HTTP 403 to Python's default `urllib` user agent, which is why the script sets its own.

## A trap we hit

Never name a script after a standard Python module (`inspect.py`, `json.py`, `types.py`). Python loads it in place of the real one and unrelated imports break.
