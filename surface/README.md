# `surface`: the page where a human approves

The trusted surface. The agent searches and asks; a person approves **here**, on a page the agent cannot reach. If approval happened in the chat, the agent could approve itself.

Three files in `surface/static/`, no framework, no build step, no internet needed: `index.html`, `app.js`, `style.css`.

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
