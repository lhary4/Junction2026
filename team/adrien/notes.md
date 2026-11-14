# Adrien's notes

Results, numbers and open questions for the others. Newest first.

## For Léon: three things seen while running the harness against the real gateway (14/11, after PR #17)

How I looked: `main` after #17, replay mode, the real `merchant.app` behind the real harness, and a stand-in judge that records its calls (there is no Gemini key on my machine). What works: acts 1 and 2, act 3 both ways (Valio's own pick 464306 goes `auto`, `"substitute_with": "468465"` goes `pending_approval`), and a quote whose price was changed outside the token is denied with a clear reason. A fourth point, the lock of the audit log, is in the next section.

**1. The judge never changes a verdict, and a coffee milk goes through on `auto`. To decide together: it is a product choice.**

- Measured: a quote for 500 L of 469363 with `"substitute_with": "463380"` (Arla Cafè milk), then `POST /authorize`. Answer: `ordered`, signed by the agent, EUR 1,259.72, judge called 0 times.
- Why: `_is_pre_accepted` in `harness/rules.py` accepts any substitute of the same category with the same `contains` list, before the judge is asked. 463380 is in category 10400 and contains milk, like the original.
- What it contradicts: the demo policy says "No flavoured milk and no coffee creamers", and `TECH-CHOICES.md` says the judge sends this product to a human at 23%. In the five quotes I tried, the judge was only called for the oat drink 468465, which `allergen-unchanged-on-substitution` already sends to a human.
- Where it comes from: the `pre_accepted` rule of the contract (PR #7), not your code.
- Proposal: pre-accept only what Valio picked. The signed quote carries `aimo.requested[].substitute_with`: when it is filled, the agent picked the substitute, so ask the judge. About five lines in `harness/rules.py`. The default act 3 stays `auto` with no network, the coffee milk goes to the judge, and 464201 picked by the agent lets the judge say yes (0.96 in your L1 test).
- The other way, with no code: `"pre_accepted": "none"` in the policy. Every substitute then goes to the judge, so the `auto` of act 3 depends on Gemini answering on stage.
- Not measured: what the judge answers on what the harness really sends. `rules.py` builds the two cards from the quote, which has no brand and no nutritional claims, and the `labels` it adds are dropped by `_structured_product` in `harness/judge.py` (it reads `nutritional_claims`). Your L1 scores were measured on the full product cards. One difference the judge will see: 469363 has `free_from: ["ML"]`, while 464306 and 464201 have an empty `free_from` (their lactose-free claim is only a nutritional claim). If the judge needs the claims, I can add `nutritional_claims` to `LineClaims` and `SubstituteFor` in a small contract PR: tell me.

**2. The approval deadline is later than the quote's expiry. One line to change.**

- `evaluate` sets `deadline = checkout.aimo.closing_time or checkout.expires_at`. The gateway signs `expires_at` as the earlier of the cut-off and 24 hours after the quote. In replay mode the quote expires on 15/11 at 13:29:07 and the card says 15/11 at 17:00.
- Measured with `AIMO_FROZEN_NOW=2026-11-15T15:00:00+02:00`: the approval is still `pending`, Approve answers HTTP 403 `quote expired at 2026-11-15T13:29:07+02:00`, and the approval stays `pending`.
- Proposal: `deadline = checkout.expires_at`. It is never later than the cut-off, and the four verdict examples still come out the same (the two times are equal in them).
- Until then, to show "the human lets it expire", freeze the clock after 17:00, for example `2026-11-15T17:05:00+02:00`.

**3. A network failure gives a bare HTTP 500, or a wrong `denied`. Unlikely on one laptop: limits to know, not to fix tonight.**

- Gateway not reachable: `POST /authorize` answers HTTP 500 "Internal Server Error", because `httpx` errors are not caught in `harness/app.py`. The agent has nothing to tell the buyer. An HTTP 502 with a readable `detail` would be enough.
- Answer lost after the gateway accepted the order: on the retry the harness signs a new mandate, the gateway refuses it (`quote chk_... was already ordered as ord_... with another mandate`), and the harness stores `denied` while Valio holds an accepted order. The gateway gives the same order back only when the same mandate comes back. Fix on your side: keep the `Authorization` you sent and send it again on a retry.
- The `checkout` object next to the token with a field missing: HTTP 500, because the `ValidationError` of `AimoCheckout.model_validate(raw_checkout)` in `_verify_quote_token` is not caught. A changed price in that object is handled well: denied, `quote-signature`.

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
