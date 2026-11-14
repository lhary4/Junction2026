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

## Saturday evening: the 2-minute video (replaces "After 17:00")

Read the section "The demo: a 2-minute video, three buttons, one AP2 trail" in `PLAN.md` first. Your lane tonight is the page only, UI and UX, in `surface/`. Adrien builds the service that produces the data and writes `scenarios/run.py`. Léon edits `scenarios/policy.demo.json` and writes the demo script and the deck.

The page is the stage of the video: a mock-up of a Valio Aimo customer portal for the restaurant of `scenarios/restaurant-case/`. Everything on screen comes from one JSON object, the demo state. You render it, you never compute a fact.

### The layout (one screen, recorded at 1920x1080, no scrolling during a scenario)

- **Left, a fixed panel**: one button per scenario, read from `state.scenarios` (today "Normal order", "Substitution", "Attack"; a fourth may appear), plus "Reset". The running scenario is highlighted.
- **Centre, the kitchen**: the restaurant's name and menu, the lines the agent asked for (product, quantity, price, the dish each one goes into), then the card of the moment: the order confirmation, the substitution and approval card with "Approve and sign" and "Reject", or the list of refused attacks.
- **Right, the AP2 trail**: `state.steps`, seven steps from top to bottom: open mandate, signed quote, verdict, closed mandates, Valio verifies, sandbox payment, signed receipt. Each step shows its title, who signed (manager, agent, Valio), a short proof (a hash) and one line of detail. Statuses: pending (grey), done (green), waiting (amber, the chef must sign), refused (red), skipped. Reveal the done steps one after the other, about 400 ms apart, so a viewer can follow.
- **A thin banner**: "Concept mock-up, Junction 2026, synthetic data". The payment step always carries the word "sandbox".

### The demo state

```json
{
  "scenarios": [{"id": "normal-order", "title": "Normal order", "hint": "..."}],
  "scenario": {"id": "substitution", "title": "Substitution", "status": "waiting_for_human"},
  "kitchen": {"name": "...", "covers_per_service": 50, "services": ["..."], "menu": [{"course": "Starter", "dish": "..."}]},
  "request": {"text": "what the agent was asked", "lines": [{"product_id": "...", "name": "...", "amount": 6, "unit": "KG", "dish": "Main"}]},
  "quote": null,
  "verdict": null,
  "authorization": null,
  "approval": null,
  "order": null,
  "attacks": [{"title": "...", "status": "refused", "problems": ["..."]}],
  "steps": [{"key": "open_mandate", "title": "...", "signer": "manager", "status": "done", "detail": "...", "proof": "a3f9c1", "at": "2026-11-14T13:29:15+02:00"}],
  "audit": {"buyer": [], "merchant": []}
}
```

`scenario.status` is `idle`, `running`, `waiting_for_human`, `done` or `refused`. A step's `signer` is `manager`, `agent`, `merchant` or `none`, its `status` is `pending`, `done`, `waiting`, `refused` or `skipped`. `quote`, `verdict`, `authorization`, `approval`, `order` and the audit events keep the shapes of `contract/models.py` (`CheckoutResponse`, `Verdict`, `AuthorizationStatus`, `ApprovalRequest`, `Order`, `AuditEvent`), so the functions you already have in `app.js` still work on them: `linesTable`, `verdictPanel`, `substitutionCompare`, `judgeBar`, `approvalCard`, the countdown, `auditEvent`. `order` will gain a `payment` object (id, status, amount, currency, instrument, terms, `sandbox: true`).

### Where the state comes from

- **Mock mode** (`?mock=1`): `contract/examples/demo-state.<name>.json`. Adrien merges these files around 20:30. Until then, write one small sample file of your own in `surface/static/` to build the layout, and delete it when his files land.
- **Live mode**: `GET http://localhost:8003/state` every second. A scenario button sends `POST http://localhost:8003/scenarios/<id>/run`. Reset sends `POST http://localhost:8003/reset`. The chef's decision goes to the harness as today: `POST http://localhost:8002/approvals/<approval_id>/decision` with `{"decision": "approve", "decided_by": "chef"}` (or `"reject"`).

### The steps, one branch and one small PR each

1. **C5** `feat/surface-demo-shell` (by 22:00): the three zones and the left panel, in mock mode. Update the "Approval page" entry of `TECH-CHOICES.md`.
2. **C6** `feat/surface-demo-cards` (by 23:30): the substitution and approval card (both products side by side, what differs, the judge's bar, the countdown, the dishes affected), the order confirmation with the sandbox payment, the attack list, and the animated trail.
3. **C7** `feat/surface-demo-live` (by 00:30): live mode, banner, polish for the recording.

The rules the page keeps do not change: it never invents a fact, a missing value reads "unknown", everything from the data goes through `esc()`, approval happens on this page only, no framework and no build step. Keep the old screens reachable if it costs nothing, otherwise remove them. Update `tests/test_surface_static.py` for what changed. Questions for Adrien go in `team/colette/notes.md`.
