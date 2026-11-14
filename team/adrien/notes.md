# Adrien's notes

Results, numbers and open questions for the others. Newest first.

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
