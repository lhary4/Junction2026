# Colette's notes

Results, numbers and open questions for the others. Newest first.

## C6: the kitchen order page, V2 (the team's review of 14/11)

What changed, point by point: `surface/README.md`. In short: the stock can be changed (table and chat), the signing steps moved to a panel on the left with an eighth step for the delivery, the checks are written for a chef, the chat answers with Gemini, a signature is confirmed in a window, and the chef can go back after an order.

Tested on 14/11 in headless Chrome at 1920x1080: the three scenarios end to end, a stock change by hand and by chat, approve, reject, the attack then the corrected order. Three ways: in replay mode, against a stand-in for the driver and the harness, and at 22:25 against the real driver, gateway and harness of `main` at `80eaff2` in live mode (`VALIO_MODE=live`). The chat was tested against the real Gemini API. No error from the page in any of them.

With the gateway in replay mode the driver answers 502 (the menu's products are not in the recorded answers, Adrien's A11). The page then shows the recorded run and says why.

### Why the page said "harness not reached"

Nothing is wrong in the harness. I started it on 14/11 with `uv run python scripts/dev.py` and asked `GET /policy` the way the page does, from another port: it answers, with the cross-origin header the page needs. Two things on the page's side:

- The harness was not running when the page was opened. Nothing was listening on port 8002.
- The page looked for the harness once, when it loaded. A harness started afterwards stayed "not reached" until a reload.

Fixed in the page: it looks again every five seconds and each service has its own light in the strip at the bottom. Nothing to change in `harness/` for this.

### For Léon: a route to change the spending limit

The team asked that the chef can change the spending limit on the page. The page has the window. It cannot work until the harness has a route: the limit must live where it is enforced, and the open mandate carries it. Until then the page says "The limit has not changed". Message to paste into a session in `harness/`:

> Read `harness/app.py`, `harness/policy.py`, `harness/signer.py` and `docs/contract.md`. Add a route so the chef can change the spending limit from the page.
>
> - Route: `PUT /policy/autonomous-limit`, body `{"autonomous_limit_minor": <whole number of cents, 1 or more>, "decided_by": "<who>"}`. Answer: the full `BuyerPolicy`, with the new limit. Refuse anything else with 422.
> - The new limit applies to the next `POST /authorize`: the spend rule uses it, and the open mandate signed for the agent carries it (the gateway refuses a mandate above its cap, so both must agree).
> - `GET /policy` returns the limit in force.
> - Keep the change where the harness keeps its state (not in `scenarios/policy.demo.json`, which is a file of the repo), so that `scripts/dev.py --fresh` goes back to the file's limit.
> - Write one line in the buyer audit log: who changed the limit, from what to what.
> - An approval that is already pending keeps the verdict it had.
> - Tests in `tests/test_harness_service.py`: the route changes what `GET /policy` returns; an order above the new limit goes to `human`; a body without a positive whole number is refused.
> - Update `docs/contract.md` (the harness routes table) with Adrien's agreement, and `TECH-CHOICES.md`.
>
> The page already calls this route (`harness.setLimit` in `surface/static/portal.js`). Nothing to change in `surface/`.

### For Adrien: the demo driver takes the chef's lines (after the video)

Your notes say "not tonight", and I agree for the video. For later: the chef can now change the stock table, and the page already sends what is missing with the order: `POST /scenarios/{id}/run` with the body `{"lines": [{"product_id", "name", "amount", "unit", "dish"}], "delivery_date": "2026-11-19"}`. The driver ignores the body today, which works: the page shows a red line saying the quote is not for the changed quantities. Message to paste into a session on `scenarios/run.py`:

> In `scenarios/run.py`, let `POST /scenarios/{id}/run` take an optional JSON body: `{"lines": [DemoRequestLine, ...], "delivery_date": "YYYY-MM-DD"}`, the same line shape as `DemoState.request.lines`. For `normal-order` and `substitution`, when `lines` is given, ask the gateway for a quote for these lines instead of the scenario's own, and put them in `DemoState.request.lines`. Without a body, nothing changes. `attack` ignores the body. Refuse a line with an amount of zero or less. Add the body to the driver's table in `docs/contract.md`.
>
> Two facts the page relies on, to keep: the page reads `request.lines` to know whether the quote is for what the chef asked, and after a rejection it reads `GET /state` again and expects `scenario.status` to be `refused`.

Other points for Adrien:
- The page shows an eighth step, "Delivery scheduled", that it reads from `order.delivery_date` and `order.status`. It is not in `DemoState` (seven steps, checked by the model). If you would rather have it in the contract, tell me and I remove the page's own step.
- The page is now served by `surface/assistant.py` on port 8004, so port 8003 is free for the driver. `scripts/dev.py` could start it as a fourth service: `("assistant", "surface.assistant:app", 8004)`.

Open, for the three of us:
- The words the services write for the team ("the agent", "the judge", "the harness") are reworded by the page into "your assistant", "Aimo Personal Assistant" and "the safety checks". If the driver's sentences change, the page's rewording may need a look.
- The synthetic numbers in `surface/static/kitchen/` (stock counts, 38/46/50 booked covers) are mine. Tell me if the video needs others.

## C5: the kitchen order page, V1 of the front end

- `surface/static/portal.html`: three steps for the chef (recipes, stock, order), the seven signing steps at the top, the agent's conversation on the side, demo buttons in a strip of their own. How to open it and where its data comes from: `surface/README.md`.
- Tested on 14/11 in headless Chrome, the three scenarios end to end, in replay mode and against a stand-in for the demo driver that follows `docs/contract.md`. **Not tested against the real driver**: it does not exist yet (step A8).
- The kitchen's recipes, stock count and bookings are synthetic files in `surface/static/kitchen/`.

Questions for Adrien (demo driver):
- Can `POST /scenarios/{id}/run` take the lines to order? Today a scenario always sends its own lines, so the chef cannot add or change a line on the page ("one piece is missing, add it"). The stock table is read-only for that reason.
- Should recipes, stock and bookings come from the driver (in `DemoState`) instead of the page's own files? Then the stock count and the request can never disagree.
- An approval the chef rejects: no recorded example. In replay the Reject button says so.
- Product photos: the product file only gives media ids (`synkkaData.medias[].id`), no link.
- When the driver takes port 8003, the page is opened through the harness on 8002. Does the harness serve `portal.html` and the `kitchen/` folder as they are?

## C2: the page in mock mode

- Done: `surface/static/` shows the three areas from `contract/examples/`. How to run it and one link per screen: `surface/README.md`.
- Checked in headless Chrome on 14/11: the four offers screens, both approval cards in their four states, both buttons, a card expiring when the countdown reaches zero, the audit page, and that HTML typed into the agent's sentence stays plain text.
- Live mode is not built: without `?mock=1` the page says so. That is step C4.

Questions for Adrien (examples and contract):
- **The comparison table has one price in act 1.** Product cards carry no price, and the act 1 quote only prices 464306, so the four other rows read "unknown, not in this quote". For a full price comparison in act 1, either the agent asks one quote per candidate, or a quote lists the prices of the other candidates. Which one do we want?
- There is no example quote for `chk_act3_oat_demo` (the oat drink order of `verdict.human.substitution.json`). The substitution card shows "lines not in the example files" and takes the total from the verdict. An example `checkout.act3-oat.json` would complete it.
- There is no `ApprovalRequest` example for a substitution. The page builds one from the verdict (rules that did not pass become the reasons). Is that what the harness will send?
- Two facts have no certainty level in the contract: the delivery date of a line (`available_date`) and the price of an alternative (`aimo.alternatives[].comparison_price_minor`). The page shows them with a "certainty not stated" badge instead of guessing.
- `chk_act3_demo` has no verdict in the examples, so its signature line reads "not checked yet".

Question for Léon:
- `approval_url` in the examples is `http://localhost:8002/#/approvals/apr_...` (the harness's port). The page understands `#/approvals/<id>`, but it is served on port 8003. Will the harness serve `surface/static/`, or should the link point to 8003?

## What Junction asks us to hand in

- Deadline: **Sunday 15/11/2026 at 10:00** (strict auto-close, no late submissions; must switch project status from **DRAFT** to **FINAL** before 10:00 — FINAL projects can still be edited until 10:00).
- Video (length, format): **2-minute video pitch — strictly NOT A SECOND LONGER THAN 2:00** (aim for ~1:50–1:55). Uploaded to YouTube or Vimeo and set to public ("available for everyone").
- Text (length): Project name, punchline, description, Challenge selected, Technologies used (no character limit stated on the summary screen, check field counters when filling DRAFT).
- Slides: **Pitch deck (PDF)** required.
- Repo link or access: Demo link + Source code link + Source code publicity choice + Credit preference.
- Contact fields required: Team members' phone numbers + Discord username.
- Pitch length and format: Top teams are contacted before the Closing Ceremony for live pitching; the primary judged pitch for everyone is the **strictly <= 2:00 video + PDF deck** (so our 4 demo acts must fit comfortably inside ~90 seconds of the 2-minute video!).

## C1: Claude Desktop as the agent

- MCP server (`agent_mcp/server.py`) connects in **380 ms** and answers `tools/list` in **3 ms** (verified in `~/Library/Logs/Claude/mcp-server-valio-aimo.log` and 9/9 stdio integration checks).
- Claude Desktop chat was not usable on Colette's laptop/account, so prompts were tested in Antigravity with the same MCP server:

| Round | Time from the sentence to the final answer |
|---|---|
| 1 | ~2 min (120 s) |
| 2 | > 6 min (no answer / hung) |
| 3 | Skipped (already failed the < 30 s gate) |

Does Claude ask questions before acting?
- Not testable on Claude Desktop on Colette's machine; Antigravity IDE agent is way too slow (> 2 min, hung on round 2, partly due to full repo + 83 MB data tabs in IDE context).
- Recommendation: either test `feat/agent-mcp-mock` for 2 minutes on Adrien/Léon's Claude Desktop, or switch to the planned fallback (`scenarios/run.py` scripted runner), which also fits the strict **<= 2:00** submission video rule.

Does it order on its own?
- Automated MCP stdio flow (`search_products` -> `request_quote` -> `authorize_checkout`) returns `status: "ordered"`, `decision: "auto"`, `signed_by: "agent"`, `order_id: "ord_4b9d2a10"` for 1,000 L.

What does it say when an approval is pending?
- For 2,000 L (`chk_act2_demo`), `authorize_checkout` returns `status: "pending_approval"`, `deadline: "2026-11-15T17:00:00+02:00"`, and `approval_url: "http://localhost:8002/#/approvals/apr_7c1e0b52"`.
