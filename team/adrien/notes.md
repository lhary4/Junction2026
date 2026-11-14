# Adrien's notes

Results, numbers and open questions for the others. Newest first.

## The gateway's log uses `common/audit.py`, and `dev.py --fresh` (14/11, PR #18)

For everyone: `uv run python scripts/dev.py --fresh` empties the local state (quotes, orders, approvals, both audit logs), then starts both services. Use it before a rehearsal or the demo. Why: in replay mode the clock is frozen at the recording time, so an approval left pending never reaches its cut-off and stays on the approval page. It removes nothing while a service still answers on 8001 or 8002, and says so: the harness keeps its approvals in memory and would write the old ones back.

Checked over real HTTP with both services: act 2 leaves 1 pending approval, 4 lines in the buyer's log and 1 in the gateway's. A plain restart keeps all of it. A restart with `--fresh` shows 0, 0 and 0.

`merchant/audit.py` no longer chains its own lines: `record()` and `events()` call the shared `AuditLog`. Same file (`state/merchant/audit.jsonl`), same lines, same fingerprints. `GET /audit` on 8001 answers as before.

For Léon, one thing in `common/audit.py` that I worked around and did not change, because it is your file: the lock of an `AuditLog` belongs to the object, and `harness/app.py` builds a new object on every request (`_audit()`), so two requests at the same moment are not kept apart. Measured: 8 threads writing 200 lines through separate objects break the chain at the second line (`verify()` returns 1). Through one shared object the chain stays whole. This is why the gateway holds one lock of its own in `merchant/audit.py`. Two ways to fix it on your side: one lock per file path inside `common/audit.py` (then the gateway's lock can go), or one `AuditLog` kept for the life of the harness.

## Lookup: `GET /offers`, prices and availability before any quote (14/11, PR #16)

The brief's first must-have ("product, price and availability lookup") had no route. Now: `GET /offers?q=&delivery_date=&amount=&unit=&limit=` on the gateway (8001). Fields and rules: `docs/contract.md`, section "The lookup". Example: `contract/examples/offers.act1.json`.

Try it: `uv run python scripts/dev.py`, then open `http://localhost:8001/offers?q=lactose-free%20milk&delivery_date=2026-11-16&amount=1000&unit=L&limit=5`.

What it answers to the brief's sentence, in replay mode and in live mode on 14/11 at 15:32 (same five rows; live: 70 products matched in the full catalog, 70 priced, 2 seconds):

| Product | Per litre | 1,000 L, excl. tax | Stock | Cut-off |
|---|---|---|---|---|
| 464306 Valio Arki Eila semi skimmed 1 l | EUR 1.01 | EUR 1,010 | available, count not given | Sun 15/11 17:00 |
| 464401 Valio Arki Eila skimmed 1 l | EUR 1.10 | EUR 1,100 | available, count not given | Sun 15/11 17:00 |
| 464237 Valio coffee milk 1 l UHT | EUR 1.30 | EUR 1,300 | available, count not given | Sun 15/11 17:00 |
| 477050 Valio Eila skimmed sour milk 1 l | EUR 1.35 | EUR 1,350 | available, count not given | Sun 15/11 17:00 |
| 463335 Valio Eila 3 % milk drink 1 l | EUR 1.40 | EUR 1,400 | available, count not given | Sun 15/11 17:00 |

With `limit=25` you also get the other cases: 469363 (384 units counted, `stock_covers: false` for 1,000 L) and the offers that cannot be ordered, for example 463038, the 10 l Novobox (`orderable: false`, `reason: "late_delivery"`, its cut-off was 12/11).

The answer is **not signed** and says so (`"binding": false`). The signed quote stays the only thing the harness, a mandate or a receipt refers to.

For Colette, three things to plug (I do not touch `agent_mcp/` or `surface/`):

1. **A sixth MCP tool, `lookup_offers`.** Arguments: `query`, `delivery_date` (ISO date), optional `amount` with `unit` (`L`, `KG` or `ST`), `limit` (5 is enough for a chat). It calls `GET {MERCHANT_URL}/offers` and returns the JSON as it is. In example mode it returns `contract/examples/offers.act1.json`. The gateway answers HTTP 422 with a readable `detail` when the request has to change, HTTP 503 when Valio's API does not answer.
2. **Rule 2 of `SERVER_INSTRUCTIONS` in `agent_mcp/server.py`.** Today it says to call `search_products`, then `request_quote` "for the best matching option", but nothing in a search result says which option is best: there is no price in it. Proposed text: "When the buyer specifies what they need, how much, and by when, complete the workflow without asking unnecessary questions: call `lookup_offers` with their words, the delivery date, the amount and its unit. Pick the first offer with `orderable: true` that fits what the buyer asked (offers are sorted: orderable first, then enough counted stock, then cheapest per litre or kilo). Never pick an offer with `orderable: false`: say its `reason` instead. Then call `request_quote` for that product, and `authorize_checkout` so the buyer's harness applies policy."
3. **Rule 1 and the `search_products` description** say a price may only be stated after `request_quote`. With the lookup: "Prices from `lookup_offers` are indicative: state them as indicative, with their `as_of` time. A price or a total only commits Valio once it is in the signed quote from `request_quote`." Two more signals worth a sentence: `stock_covers: false` means the quote will take what there is and propose substitutes for the rest, and `matched` larger than `priced` means the words were too broad.

Answer to your question "The comparison table has one price in act 1": neither one quote per candidate, nor more prices inside the quote. The table reads `GET /offers` (`offers.act1.json` in mock mode): each row has its price per litre, delivery date, cut-off and stock, next to the reliability, carbon and labels already on the card. Label these rows "indicative, not signed" (the answer carries `binding: false`), and keep "signed by Valio" for the lines of the quote. The quote keeps pricing only what is ordered.

Also in your notes: the delivery date had no certainty level. In the lookup, `available_date` and `closing_time` are claims now (`declared` and `measured`, source `aimo_availability_api`). In the signed quote they are still plain values, so keep the "certainty not stated" badge there for now.

`GET /products/search` keeps its shape, but its results change: hyphens, punctuation and case no longer count ("lactose-free milk" found nothing before), and every category is returned, closest names first. In the full catalog a search for "lactose-free milk" now also returns a lactose-free milk chocolate. That is why the agent should compare through `lookup_offers`, where a product sold by the kilo is marked `unit_mismatch` when litres are asked.

For Léon: nothing changes for the harness. One new value in the list of claim sources, `aimo_availability_api`.

Seen while testing, not changed here: 463779 answers a stock of 666,666,666 units. It looks like a second "plenty" value of the mock, next to 9,999,999,999, but the gateway reads it as a real count (`measured`), in quotes too.

## A5: the gateway takes orders (14/11, 14:50)

Start it: `uv run python scripts/dev.py` (gateway on 8001, and the harness on 8002 once `harness/app.py` exists). Routes and cases: `docs/contract.md`, section "The order".

Checked in replay mode, with mandates built by `trust/` exactly as the harness will build them. The first three rows also ran over real HTTP against `scripts/dev.py`, the others run in `tests/test_merchant_orders.py`:

| Case | Answer |
|---|---|
| Act 1, 1,000 L, mandate closed by the agent | 200, order `accepted`, `signed_by: agent`, the receipt verifies against the gateway's JWKS |
| Act 2, 2,000 L, mandate closed by the agent | 403, `Amount 202000 exceeds maximum 150000` |
| Act 2, 2,000 L, mandates signed by the manager | 200, `signed_by: human` |
| Act 4, mandate built over a quote whose price was changed | 403, `Checkout checkout_hash mismatch` and `payment mandate is for another quote` |
| Same mandate sent twice | 200, same order, same receipt, one order on disk |
| A second mandate for an ordered quote | 403, `already ordered as ord_...` |

For Léon (16:30 cross-call):
- After `POST /checkouts/{id}/complete`, HTTP 200 is an `Order`, HTTP 403 is `{"problems": [...]}`, HTTP 404 is an unknown quote. Verify `order.receipt_jwt` with `trust.verify_receipt` and the JWKS from `GET /.well-known/jwks.json`, then compare its `reference` with `order.mandate_reference`.
- `common/audit.py` was not on `main` when I wrote A5, so the gateway chains its own lines in `merchant/audit.py` (same fields as `AuditEvent`, SHA-256 of the event as JSON with sorted keys and no spaces, without `hash`). When yours is merged I switch that one file to it. Tell me if your canonical JSON differs, so both logs verify with the same function.

For Colette (C4): `GET /audit` on 8001 returns the gateway's lines, oldest first. Actions: `quote_issued`, `mandate_verified`, `order_accepted`, `order_replayed`, `order_refused`.

Open question: the gateway does not ask Valio for stock again when the order arrives. The quote holds until it expires (24 hours at most, or the cut-off). Say so if a mentor asks.
