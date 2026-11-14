# Colette: what the agent sees, what the human sees, and the story

Read `PLAN.md` first. Your lane is everything a judge will actually look at: the agent's tools, the page where a human approves, the demo script and the pitch. You know Valio's expectations best, so you also hold the product decisions: the buyer's policy, which substitutions are acceptable, what the demo says.

Your steps are built on example files that already exist in `contract/examples/`, so you never wait for the other two. Let your Claude Code session write the code. Your job is to tell it what the page must show and to check it does.

## What you own

- `surface/`, `agent_mcp/`, `scenarios/`, `docs/demo-script.md`, `docs/pitch-outline.md`, `contexte/mentor-notes.md`.
- Do not edit `contract/`, `trust/`, `merchant/`, `harness/`, `common/`. If an example file lacks something the page needs, tell Adrien.

## Before 13:15

- Install `uv` (https://docs.astral.sh/uv/) and Claude Desktop.
- `cp .env.example .env` and fill the keys from the team chat.
- Open the Junction submission form and write in `team/colette/notes.md` what must be handed in: a video (how long?), a text (how long?), slides, a repo link, the exact deadline, and how long the pitch is. Say it to the others at 13:15. It decides how long each act of the demo can be.

## Rules for every step

- One step = one branch = one small PR. Start from an up-to-date `main` (`git switch main && git pull`).
- Write results and questions in `team/colette/notes.md`.
- Everything in the repo is in English.
- Stuck for more than 15 minutes? Say it out loud.

## C1. The agent's tools, on example data (13:15 to 14:05)

Branch `feat/agent-mcp-mock`. Goal: know by 14:05 whether Claude Desktop can play the buying agent live.

Ask your session to build `agent_mcp/server.py`:
1. Five tools, named and described in `docs/contract.md` (section "MCP tools"): `search_products`, `request_quote`, `authorize_checkout`, `get_authorization_status`, `get_order`.
2. In this first version every tool answers from the files in `contract/examples/`: 1,000 litres gives `checkout.act1.json`, 2,000 litres gives `checkout.act2.json`, product 469363 gives `checkout.act3.json`, and the matching entries of `authorization-status.json`.
3. The server must find the example files from its own location, not from the current folder, because Claude Desktop starts it from somewhere else.
4. Use `spikes/stack/mcp_server.py` as the model. The class is `MCPServer` from `mcp.server.mcpserver`. Older examples use `FastMCP`, which no longer exists in this version.
5. Run it with `uv run --python 3.14 --with "mcp>=2.3" python agent_mcp/server.py`.

Then plug it into Claude Desktop: in its settings, the Developer section has "Edit Config", which opens `claude_desktop_config.json`. Add a server whose command is `uv` and whose arguments are the ones above, with the full path to `server.py`. Restart Claude Desktop. If it cannot find `uv`, use the full path given by `which uv`.

Test with the brief's sentence: "I need 1,000 litres of lactose-free milk by Monday. Find an option that meets our requirements based on price and availability." Do it three times with a stopwatch.

The tool descriptions are instructions to the agent. They must make it: never state a price that did not come from a tool, always pass the human's own sentence as `request_text`, and tell the human clearly when an approval is waiting and where.

Write in `agent_mcp/README.md`: the config block that worked on your machine and the three timings. In your notes: does Claude ask questions before acting, does it order on its own, what does it say when the answer is `pending_approval`?

At 14:05 we decide together. A full round under about 30 seconds without going off track: Claude Desktop is our live agent. Otherwise the demo uses the scripted runner and a recording.

## C2. The page, on example data (14:05 to 15:35)

Branch `feat/surface-mock`. Goal: every screen of the demo exists and can be shown, before any service runs.

Ask for plain HTML, CSS and JavaScript in `surface/static/` (`index.html`, `app.js`, `style.css`). No framework, no build step. Serve it from the repo root with `python3 -m http.server 8003` and open `http://localhost:8003/surface/static/index.html?mock=1`. With `mock=1` the page reads `contract/examples/`.

Three areas:
1. **Offers.** A comparison table built from `product-cards.json` and a quote: price per litre, delivery date, delivery reliability, carbon footprint, labels, allergens. Next to each fact, a small badge with its certainty: measured, declared, estimated or unknown. A missing value reads "unknown", never an empty cell. One line says "Signed by Valio Aimo, verified".
2. **Approvals.** A card built from `approval-request.pending.json` and `checkout.act2.json`: the lines, the total, the rule that sent it to a human in plain words, and a countdown to the deadline. Two buttons: "Approve and sign" and "Reject". Four states to draw: pending, approved (who and when), rejected, expired. A second version for a substitution, from `verdict.human.substitution.json`: the two products side by side, the allergens that differ, the carbon footprints, and the judge's probability as a bar.
3. **Audit.** Two columns, "Buyer" and "Valio Aimo", from `audit-events.json`, lined up by quote. Each line: time, who, what, why, which rule.

Things to insist on: large type (it will be projected), strong contrast, buttons big enough to click on stage, each state reachable by a link (for example `?mock=1&state=expired`) so you can rehearse.

Why this page matters: the human must approve somewhere the agent cannot reach. If approval happened in the chat, the agent could approve itself. AP2 calls this a trusted surface.

Done when: every state shows from the example files and the PR is merged.

## C3. Words, no code (15:35 to 16:15)

Branch `feat/demo-script`.

1. `docs/demo-script.md`: the four acts from `PLAN.md`. For each: the sentence typed, what appears and where, one sentence the presenter says, and what we do if the live version fails. The total must fit the pitch length you found this morning.
2. `scenarios/prompts.md`: the exact sentences to type into Claude Desktop, act by act.
3. `scenarios/policy.demo.json`: start from `contract/examples/policy.demo.json`. This file is the product decision: the spend limit, the blocked allergens, and above all `preferences_text`, the buyer's wishes in plain language that the judge reads. Tell Léon when you change it.
4. `contexte/mentor-notes.md`: ask the mentors the three open questions at the end of `contexte/valio-aimo-resources.md`, plus one of ours: would Valio accept an order signed this way? Write down who answered and what they said.
5. `scenarios/pairs.csv`: Adrien drops `scenarios/pairs.todo.csv` around 15:25. For at least 10 pairs, fill the `label` column: `ok` (the kitchen would not notice), `ask` (a human should decide), `no` (never). Léon uses it to set the judge's thresholds, and the result table goes in the pitch.

## C4. From example files to the live services (16:15 to 16:55)

Branch `feat/surface-live`.

1. The page without `mock=1` calls the live routes listed in `docs/contract.md`: pending approvals from the harness (refreshed every 2 seconds), the decision buttons, the two audit logs, the quote from the gateway.
2. `agent_mcp/server.py` gets a live mode (`AGENT_MCP_MODE=live`) that calls the gateway and the harness. Keep the example mode: it is our safety net.
3. `docs/pitch-outline.md`, five slides: the problem, the idea (the verdict decides who signs), the demo, the standards we use and what we add to them, what comes next.

## 17:00 checkpoint

With Adrien and Léon, write `scenarios/run.py` on one screen: act 1 through the real pieces. Your page must show the order and both logs. Record a first backup video right after, even if it is rough.

## After 17:00

In order: act 1 live from Claude Desktop, the attack buttons for act 4 with Léon, a new backup video at each milestone, rehearsals.
