# `surface`: the page where a human approves

The trusted surface. The agent searches and asks; a person approves **here**, on a page the agent cannot reach. If approval happened in the chat, the agent could approve itself.

Three files in `surface/static/`, no framework, no build step, no internet needed: `index.html`, `app.js`, `style.css`.

## The clean portal (the page the address opens)

`surface/static/aimo/` is a second take on the kitchen page, built on 15/11 to show less: no conversation, no signing panel stuck on the left. It reads the same services and the same recorded runs as `portal.html`, and changes nothing in it. <http://localhost:8004/> opens it once the services run (same commands as below). The first page is still at <http://localhost:8004/surface/static/portal.html>; `HOME_PAGE` in `surface/assistant.py` says which of the two the address alone opens.

Three versions of the same product. **B Console is the main one** and opens when nothing is asked. `?v=a` and `?v=c` open the two others, and the strip at the bottom then offers all three:

| Version | Where the chef lands | Where the assistant shows |
|---|---|---|
| **A Brief** | One column and one sentence ("Thursday's order is ready."), one button | Its card is the page: what it prepared, then each step as it happens |
| **B Console** | A sidebar and a dashboard: what is short, what needs a signature, the stock table | A chip in the sidebar, and a card beside the order on its own screen |
| **C Guided** | Menu, stock, order, one step at a time (the flow of the first page) | One sentence under the steps, and the card beside the order |

What replaces the conversation and the signing panel, in all three:

- **The assistant's card.** A list of what it did, one line per real step, each with who did it (Aimo, You, Valio, Checks). Before an order it holds what it prepared from the menu and the stock count. The steps of the order arrive one after the other, like the trail of the first page. In version A each line also carries the AP2 term and the start of its proof.
- **Three seals: You, Aimo, Valio.** A seal turns lime when its signature exists. It is the only lime on the page. They answer "who signed?" at a glance: Aimo inside the limit, you on the approval screen, or nobody.
- **One field to ask.** The chat of `surface/assistant.py`, with the last answer only and what it really changed. Nothing scrolls.
- **Your rules for this order.** Four cards read from the harness's policy before the order, and filled with what each check found once the verdict is in.

Screens shared by the three versions:

| Screen | What it shows | From |
|---|---|---|
| **Orders** | The next delivery (only the steps that happened are ticked), then every order with who signed it and its proof | The demo state, `GET /authorizations` on the harness, `GET /orders/{id}` on the gateway, and `history.sample.json` |
| **Approvals** | The order that waits: why, the tier Valio ranked the substitute in, what changes if you take it on four sides (cost, the dish, the kitchen, storage and delivery, the same four lines as the first page), the checks, then Approve and sign, Reject, Reject and edit the order. Past decisions below | The demo state, `GET /approvals`, `POST /approvals/{id}/decision` |
| **Rules** | The chef's gauges: spending limit, banned allergens, what to do when allergen data is missing or a substitute changes it, substitutes (allowed, accepted without asking, the two scores of the judge, the preferences text), late delivery | `GET /policy`, `PUT /policy`, `POST /policy/reset` |
| **Audit** | Both logs as one stream, the proof of each line, and a button that recomputes every fingerprint in the browser. The attack scenario shows here | `GET /audit` on the harness and on the gateway |

Things to know:

- **Rules are saved by the harness, never by the page.** Saving needs the routes of PR #50 (`PUT /policy`). Without them the screen still shows the rules and says that nothing was saved. With the harness stopped, it shows the demo policy file, read only.
- **`history.sample.json` is made up** and says so: rows carry a "sample" tag on the page. Products and unit prices are those of the quote recorded on 14/11, everything else is invented. `tests/test_surface_aimo.py` checks that its totals add up.
- **The delivery steps after "Accepted by Valio" are what comes next**, not tracking: the page has no data on trucks.
- **Scenarios for the team:** the strip at the bottom, or the keys `1`, `2`, `3` (scenario), `r` (reset), `v` (next version), `h` (hide the strip, for a recording). `?strip=0` starts with the strip hidden.
- **Hosted**, the page finds the services under `/driver`, `/harness` and `/assistant` like the first page. The gateway is not published, so the audit screen then shows Valio's lines for the order on screen only.
- Not carried over from the first page: editing the stock table by hand (the chat still changes it) and the Spotlight recipe.

## The kitchen order page (working demo)

`surface/static/portal.html` is the stage of the demo: the chef's order page inside a Valio Aimo customer portal, for the restaurant of `scenarios/restaurant-case/`.

### Run it

From the root of the repo, in two terminals:

```bash
uv run python scripts/fetch_data.py                     # once: the Valio data files, into data/
VALIO_MODE=live uv run python scripts/dev.py --fresh    # the gateway (8001), the harness (8002) and the demo driver (8003)
uv run uvicorn surface.assistant:app --port 8004        # the page and its chat
```

Then open <http://localhost:8004/surface/static/portal.html> (the address alone opens the clean portal above). The last command alone is enough to see the page: without the other services it replays recorded runs. The strip at the bottom shows a green light for each service that answers, and the page looks again every five seconds, so a service started later shows up without a reload.

The demo driver needs the gateway in live mode: in replay mode (`VALIO_MODE=replay`, the value in `.env.example`) the gateway has no recorded answers for the menu's products. The page then shows the recorded run instead, with a line that says why.

### What the chef does, like a checkout

1. **Recipes**: the recipes on the menu. Choosing one shows what goes into it.
2. **Stock**: every ingredient with what is needed, what the last count found and what is missing. The chef can change the count and the quantity to order, in the table or by telling the assistant ("we have 5 kg of butter left").
3. **Order**: "Order with my assistant" sends the missing lines. The page then shows the quote signed by Valio, the safety checks in plain words, the card where the chef signs when a check needs them, the receipt, or the refused attacks.

Each confirmed step gets a green tick with its time, and a short message confirms it. The chef can go back to the recipes and the stock at any time. While an order is open (the assistant is at work, or a signature is awaited) the quantities are locked. After an order is done or refused, changing a quantity prepares a new order.

Always on screen:

- **Who signs**, on the left: the eight steps of the order, in the chef's words with the AP2 term under each. They light up one after the other in about three seconds, with who signed and the start of each signature. Steps 1 to 7 come from the demo state. Step 8, "Delivery scheduled", is read by the page from the order Valio accepted (its delivery date and status).
- **The spending limit**, above the steps, with a Change button. See "Not built yet" below.
- **Aimo Personal Assistant**, on the right: the conversation, with a field to write to it.
- The services with their covers, booked and projected. The week's menu shows with the recipes only.
- The strip at the bottom is for the team only: scenario buttons, Reset and the lights of the services.

When the chef must sign: **Reject** stays at the top of the work area, **Approve and sign** is at the bottom of the card, after everything there is to read. Both open a window that asks once more, and the signing window shows exactly what is signed (lines, total, delivery date, start of the quote's hash). The comparison of a substitute shows first whether the allergens are the same, then **what changes if you take it**, one line a side: the cost (Valio's price per kilo or litre of both products, when the quote carries both), the dish (the assistant's two answers and the line under which it asks), the work in the kitchen (how the product comes), storage and delivery (storage class, Valio's stock, the delivery day, the share of past orders Valio delivered). Every figure is read from the signed quote or from the assistant's answers: the page says which of two prices is lower and works out nothing. What the data does not hold is said (no price for the product asked for, no preparation time, no delivery history). The note above names the tier Valio ranked the substitute in (good, better, best) and why. A switch shows all details of both products. The chat is given the same four lines, so it can explain the trade-off without adding a fact.

### Words

The buyer is a chef, not an engineer. The buying agent and the judge are both shown as **Aimo Personal Assistant**. Each rule of the harness has a plain sentence for each outcome (`CHECK_WORDS` in `portal.js`), for example `spend-limit` reads "The total is within your spending limit". A rule the page does not know shows the harness's own sentence. A test checks that every rule of `harness/rules.py` has its words. Text written by the services for the team ("the agent", "the judge", "the harness") is reworded on the page; numbers and facts are never touched.

### Where the data comes from

| Source | What | Calls |
|---|---|---|
| Demo driver, port 8003 | the demo state: quote, verdict, approval, order, attacks, the seven steps | `GET /state`, `POST /scenarios/{id}/run` (the page sends `lines` and `delivery_date` in the body; the driver does not read them yet), `POST /reset` |
| Harness, port 8002 | the spending limit, the chef's signature | `GET /policy`, `POST /approvals/{id}/decision`, and `PUT /policy/autonomous-limit` (asked, not there yet) |
| Assistant, port 8004 (`surface/assistant.py`) | the chat, and the page's files | `GET /health`, `POST /chat` |
| Kitchen (synthetic) | recipes, stock count, bookings | `kitchen/recipes.json`, `kitchen/stock.<scenario>.json`, `kitchen/bookings.json` |

- **Replay**: when the demo driver does not answer, or cannot run a scenario, the page replays the runs recorded on 14/11 (`contract/examples/demo-state.*.json`). `?replay=1` forces it. If the quantities in the table are exactly those of a recorded run, that run is replayed (this is how a corrected attack becomes the normal order). If they are not, the page says that the quote on screen is not for the changed quantities. No run was recorded for a rejection: in replay the page draws it itself (nobody signs, no order).
- **Other addresses**: `?driver=http://host:port&harness=http://host:port&assistant=http://host:port`.
- The page never works out a fact of Valio's. Prices, Valio's stock, totals, verdicts and signatures come from the demo state. The only arithmetic on the page is the kitchen's own: to order = need - in stock.
- The kitchen files are written so that what is missing is exactly what each recorded scenario asks Valio for. They are synthetic and say so.
- **Both audit logs**: under the order, the switch "What was recorded" opens the kitchen's log and Valio Aimo's log side by side, for the order on screen: the time, who acted, what and why, and the start of each line's hash (the full hash and the one before it show on hover). The lines are those of `audit` in the demo state, written by the harness and the gateway. The page rewords "the agent" as on the rest of the page and checks no chain itself. After the attack the kitchen's log is empty and says why: the order never reached the safety checks. `?record=1` opens the logs from the start, for a recording.
- Fonts and their licences: `surface/static/fonts/README.md`.

### The chat (`surface/assistant.py`)

A small service that answers the chef with Gemini (`GEMINI_API_KEY` in `.env`, model `gemini-3.5-flash-lite`, about one second an answer; `ASSISTANT_MODEL` in `.env` changes it). With each message the page sends what it shows; the chat may only repeat that.

- It never states a price, a stock or an allergen by itself. If it is not on the page, it says it does not know yet.
- It never signs, approves, rejects or orders. The chef does that with the buttons.
- It may change two things when the chef asks: the stock count and the quantity to order. The service checks each change again (a known product, zero or more, no order open), and the page writes what really changed under the answer.
- No key, a timeout or an unreadable answer gives an error on the page, never an invented reply.
- The service serves `surface/static`, `contract/examples` and the demo policy, and nothing else from the repo: `.env` cannot be read through it.

### Not built yet

- **Changing the spending limit.** The window is there and sends `PUT /policy/autonomous-limit` to the harness. The harness has no such route yet, so the page says the limit has not changed. The page never keeps a limit of its own: only the harness enforces it. What to build is in `team/colette/notes.md`.
- **A quote for changed quantities.** The page sends the chef's lines to the demo driver. The driver plays each scenario's own lines (decided on 14/11, `team/adrien/notes.md`), so the quote is for those lines and the page says so. One case works today: the attack asks for twelve weeks at once, the chef corrects the quantities back to what the recipes need, and that is exactly the normal order.

This page has its own files (`portal.html`, `portal.css`, `portal.js`) and does not use `app.js` or `style.css`.

## Run it (mock mode)

From the root of the repo:

```bash
python3 -m http.server 8003
```

Then open <http://localhost:8003/surface/static/index.html?mock=1>.

With `mock=1` the page reads `contract/examples/`. Nothing is checked or signed for real in this mode. Without `mock=1` the page says live mode is not built yet: that is step C4.

## The three areas

| Area | What it shows | Built from |
|---|---|---|
| **Offers** | The quote, Valio's signature line, the verdict and its rules, the ranked substitutes, and the comparison table. Every fact has a badge: measured, declared, estimated or unknown. | `product-cards.json`, `checkout.act*.json`, `verdict.*.json`, `authorization-status.json`, `order.json` |
| **Approvals** | One card per order waiting for a signature: the sentence the agent was given, the rule that sent it to a human, the lines, the total, a countdown to the order cut-off, and two buttons. | `approval-request.pending.json`, `checkout.act2.json`, `verdict.human.substitution.json`, `policy.demo.json` |
| **Audit** | The buyer's log and Valio Aimo's log side by side, grouped by quote. | `audit-events.json` |

## Rehearsal links

Every screen has its own link. They are also listed in the strip at the bottom of the page in mock mode.

| Screen | Link (after `http://localhost:8003/surface/static/index.html`) |
|---|---|
| Act 1, quote ordered by the agent alone | `?mock=1&quote=act1#/offers` |
| Act 2, quote above the limit | `?mock=1&quote=act2#/offers` |
| Act 3, partial stock and ranked substitutes | `?mock=1&quote=act3#/offers` |
| Act 4, tampered quote refused | `?mock=1&quote=act4#/offers` |
| Spend approval: pending, approved, rejected, expired | `?mock=1&case=spend&state=pending` (or `approved`, `rejected`, `expired`) |
| Substitution approval, same four states | `?mock=1&case=substitution&state=pending` |
| One approval by its id (the link the agent gives) | `?mock=1#/approvals/apr_7c1e0b52` |
| Both audit logs | `?mock=1#/audit` |
| Watch a card expire on stage | `?mock=1&case=spend&now=2026-11-15T16:59:50%2B02:00` |

`now=` starts the page's clock at that instant (write `%2B` for the `+` of the time zone). Without it the page uses the real time, so after Sunday 17:00 the pending cards show as expired.

In mock mode the two buttons change the card on this page only. Reload to start again.

## Rules the page keeps

- **It never invents a fact.** Every number comes from a loaded file. A price is only shown for a product that is in the signed quote.
- **Unknown reads "unknown".** No empty cell. Missing allergen data is never shown as "free from".
- **"Verified" comes from the harness.** The page does not check Valio's signature itself. It says "verified" only when the harness's verdict or audit log says so, otherwise "not checked yet".
- **Text from the agent is only text.** Everything from the data goes through `esc()` in `app.js` before it reaches the page, so the agent's sentence cannot add a button or a script to an approval card.

## Tests

`uv run pytest tests/test_surface_static.py`. The tests that run the page's JavaScript need Node and are skipped without it.
