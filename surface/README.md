# `surface`: the page where a human approves

The trusted surface. The agent searches and asks; a person approves **here**, on a page the agent cannot reach. If approval happened in the chat, the agent could approve itself.

Three files in `surface/static/`, no framework, no build step, no internet needed: `index.html`, `app.js`, `style.css`.

## The kitchen order page (working demo)

`surface/static/portal.html` is the stage of the demo: the chef's order page inside a Valio Aimo customer portal, for the restaurant of `scenarios/restaurant-case/`.

### Run it

From the root of the repo, in two terminals:

```bash
uv run python scripts/dev.py                          # the gateway (8001) and the harness (8002)
uv run uvicorn surface.assistant:app --port 8004      # the page and its chat
```

Then open <http://localhost:8004/>. The second command alone is enough to see the page: without the other services it replays recorded runs. The strip at the bottom shows a green light for each service that answers, and the page looks again every five seconds, so a service started later shows up without a reload.

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

When the chef must sign: **Reject** stays at the top of the work area, **Approve and sign** is at the bottom of the card, after everything there is to read. Both open a window that asks once more, and the signing window shows exactly what is signed (lines, total, delivery date, start of the quote's hash). The comparison of a substitute shows three things first (same allergens or not, price, how sure the assistant is); a switch shows all details of both products.

### Words

The buyer is a chef, not an engineer. The buying agent and the judge are both shown as **Aimo Personal Assistant**. Each rule of the harness has a plain sentence for each outcome (`CHECK_WORDS` in `portal.js`), for example `spend-limit` reads "The total is within your spending limit". A rule the page does not know shows the harness's own sentence. A test checks that every rule of `harness/rules.py` has its words. Text written by the services for the team ("the agent", "the judge", "the harness") is reworded on the page; numbers and facts are never touched.

### Where the data comes from

| Source | What | Calls |
|---|---|---|
| Demo driver, port 8003 | the demo state: quote, verdict, approval, order, attacks, the seven steps | `GET /state`, `POST /scenarios/{id}/run` (the page sends `lines` and `delivery_date` in the body), `POST /reset` |
| Harness, port 8002 | the spending limit, the chef's signature | `GET /policy`, `POST /approvals/{id}/decision`, and `PUT /policy/autonomous-limit` (asked, not there yet) |
| Assistant, port 8004 (`surface/assistant.py`) | the chat, and the page's files | `GET /health`, `POST /chat` |
| Kitchen (synthetic) | recipes, stock count, bookings | `kitchen/recipes.json`, `kitchen/stock.<scenario>.json`, `kitchen/bookings.json` |

- **Replay**: when the demo driver does not answer, the page replays the runs recorded on 14/11 (`contract/examples/demo-state.*.json`). `?replay=1` forces it. If the quantities in the table are exactly those of a recorded run, that run is replayed (this is how a corrected attack becomes the normal order). If they are not, the page says that the quote on screen is not for the changed quantities. No run was recorded for a rejection: in replay the page draws it itself (nobody signs, no order).
- **Other addresses**: `?driver=http://host:port&harness=http://host:port&assistant=http://host:port`.
- The page never works out a fact of Valio's. Prices, Valio's stock, totals, verdicts and signatures come from the demo state. The only arithmetic on the page is the kitchen's own: to order = need - in stock.
- The kitchen files are written so that what is missing is exactly what each recorded scenario asks Valio for. They are synthetic and say so.
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
- **A quote for changed quantities.** The page sends the chef's lines to the demo driver. Until the driver uses them, the quote is for the scenario's own lines and the page says so.

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
