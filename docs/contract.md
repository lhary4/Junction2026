# The contract: what the three lanes agree on

This file and `contract/examples/` are the interface between the Valio gateway, the harness and the surface. If you code against them, your piece will plug into the others. Owner: Adrien. To change anything here, say it out loud first, then one small PR.

Until Adrien's step A1 is merged, the JSON examples are the contract. After A1, the Pydantic models in `contract/models.py` are the contract and a test proves the examples still validate.

## Conventions

- **Money** is an integer in minor units (cents), as in AP2 and UCP. `101` means EUR 1.01. Our own fields end in `_minor`. Totals exclude tax.
- **Quantities**: `quantity` is always in sales units (what Valio sells, for example `ST`). `base_quantity` with `base_unit` is what the buyer asked for (`L` or `KG`).
- **Times** are ISO 8601 with an offset, Helsinki time (`2026-11-15T17:00:00+02:00`).
- **Allergen codes** are the GS1 codes from the catalog: `AM` milk, `AW` cereals with gluten, `GO` oats, `AP` peanuts, `AN` tree nuts, `ML` lactose.
- **Identifiers**: `chk_...` for a quote, `apr_...` for an approval request, `ord_...` for an order.
- The numbers in the examples are illustrative, except the catalog facts, the reliability and the carbon values, which are real. Adrien's step A3 records real prices and stock.

## A claim: the unit of the trust protocol

Every fact Valio states about a product travels with where it comes from and how sure it is. That is what lets an agent trust it without a manual check, or decide not to.

```json
{ "value": 1.1, "unit": "kg_co2e_per_kg", "source": "product_group_average", "as_of": "2026-11-14T11:21:00+02:00", "certainty": "estimated" }
```

| `certainty` | Meaning | Example |
|---|---|---|
| `measured` | Valio counted or recorded it | stock of a `Stock` product, a price from the price API, delivery reliability |
| `declared` | A supplier or data pool states it | country of origin and allergens from GS1 Synkka |
| `estimated` | Derived, not specific to this product | carbon footprint, an average of the product group |
| `unknown` | No data. `value` is `null` | stock of a `Terminal` product, a missing reliability figure |

| `source` | Where it comes from |
|---|---|
| `aimo_stock_count` | `/api/availability`, `logisticModel` = `Stock` |
| `supplier_warehouse` | `/api/availability`, `logisticModel` = `Terminal` (quantity unknown) |
| `aimo_price_api` | `/api/price` |
| `gs1_synkka` | the product file |
| `aimo_delivery_history` | the delivery reliability file |
| `product_group_average` | the carbon footprint file |
| `none` | nothing available |

Allergens are not a claim but have the same idea: `{"contains": [...], "free_from": [...], "data": "complete" | "missing"}`. 46% of the catalog has no allergen data. `missing` must never be read as "free from".

## The objects

| Object | Example file | Who produces it | Who reads it |
|---|---|---|---|
| `ProductCard` | `product-cards.json` | gateway (`GET /products/search`) | agent, surface |
| `QuoteRequest` | `quote-request.json` | agent | gateway |
| `AimoCheckout` (the signed quote) | `checkout.act1.json`, `.act2`, `.act3` | gateway (`POST /checkouts`) | harness, surface |
| `BuyerPolicy` | `policy.demo.json` | Colette writes it, the harness loads it | harness, surface |
| `Verdict` | `verdict.auto.json`, `.human.spend`, `.human.substitution`, `.deny` | harness | surface, audit |
| `ApprovalRequest` | `approval-request.pending.json` | harness | surface |
| `AuthorizationStatus` | `authorization-status.json` (six cases) | harness (`POST /authorize`) | agent, surface |
| `Authorization` (the mandates) | `authorization.json` | harness | gateway |
| `Order` | `order.json` | gateway | harness, agent, surface |
| `AuditEvent` | `audit-events.json` | both sides | surface |

### The signed quote

The quote is UCP's `Checkout` object as typed by the AP2 SDK (`ap2.sdk.generated.types.checkout.Checkout`): `id`, `merchant`, `status`, `currency`, `line_items`, `totals`, `links`, `expires_at`. We do not rename or remove any of those fields. Everything of ours sits under one extra top-level key, `aimo`, which the `Checkout` model allows. Per-line facts are in `aimo.lines`, keyed by the line item `id`.

The gateway signs the whole payload as an ES256 JWT. `checkout_hash` is the base64url SHA-256 of that JWT string. An approval, a mandate and a receipt all refer to the quote by this hash, so none of them can be reused for another cart.

A quote is valid until the order cut-off (`closing_time`), and at most 24 hours. That is the brief's "fixed prices": the price holds while a human takes the time to approve.

`aimo.shortfalls` says what could not be covered. `aimo.alternatives` ranks substitutes from Valio's own assortment as `best`, `better`, `good`. The catalog already lists substitutes for some products (field `substitutions` in the product file): use them first.

A line that replaces another product says so in `substitute_for`, with the replaced product's id, name, category and allergens. Because the gateway signs it, the harness can compare the two without another lookup. For a line that is not a substitute, `substitute_for` is `null`.

### The verdict

`decision` is `auto`, `human` or `deny`. It is the most restrictive outcome among the rules: `deny` beats `human`, `human` beats `auto`. The judge can only make a verdict stricter, never looser.

| `rule_id` | Outcome when triggered | What it checks |
|---|---|---|
| `quote-signature` | `deny` | the quote is signed by an allowed merchant key and unchanged |
| `quote-not-expired` | `deny` | `expires_at` is in the future |
| `merchant-allowed` | `deny` | the merchant is in the policy |
| `allergen-not-blocked` | `deny` | no line contains an allergen the policy blocks |
| `allergen-data-known` | `human` | every line has `allergens.data` = `complete` |
| `allergen-unchanged-on-substitution` | `human` | a substitute contains the same allergens as the product it replaces |
| `delivery-on-time` | `human` | the promised date is not later than the requested one |
| `spend-limit` | `human` | the total is within `autonomous_limit_minor` |
| `substitution-within-preferences` | `human` | the Gemini judge, for substitutes that are not pre-accepted |

A judge answer keeps what we asked and what came back, because the model returns no explanation: `question_key`, `instructions`, `probability`, `confidence`, the two thresholds, `routed`, `model`. `routed` is `auto` or `human`. At or above `judge_auto_threshold` the substitute is accepted. Below it, a human decides: between the two thresholds the message says the judge is unsure, below `judge_floor` it says the substitute is clearly outside the preferences. If the judge is unreachable, the answer is `human`.

### Who signs

| Verdict | Who signs the order | AP2 name |
|---|---|---|
| `auto` | the agent's key, held by the harness, inside the open mandates the manager signed | human not present |
| `human` | the manager, on the surface, for this exact quote | human present |
| `deny` | nobody | no mandate, so no order |

The spend cap is carried by the open payment mandate (`AmountRange`), so the gateway itself refuses an agent-signed order above the cap.

## Routes

Valio gateway, port 8001 (`merchant/`):

| Route | Input | Output |
|---|---|---|
| `GET /products/search?q=&limit=` | text query | `{"query", "count", "products": [ProductCard]}` |
| `POST /checkouts` | `QuoteRequest` | `{"checkout_id", "checkout_jwt", "checkout": AimoCheckout}` |
| `GET /checkouts/{id}` | | same as above |
| `POST /checkouts/{id}/complete` | `Authorization` | `Order`, or HTTP 403 with `{"problems": [...]}` |
| `GET /orders/{id}` | | `Order` |
| `GET /.well-known/jwks.json` | | the gateway's public keys |
| `GET /audit` | | `[AuditEvent]` |

Harness, port 8002 (`harness/`):

| Route | Input | Output |
|---|---|---|
| `POST /authorize` | `{"checkout_id", "request_text"}` | `AuthorizationStatus` |
| `GET /authorizations/{checkout_id}` | | `AuthorizationStatus` |
| `GET /approvals?status=pending` | | `[ApprovalRequest]` |
| `POST /approvals/{id}/decision` | `{"decision": "approve" or "reject", "decided_by"}` | `AuthorizationStatus` |
| `GET /policy` | | `BuyerPolicy` |
| `GET /audit` | | `[AuditEvent]` |

Both services allow cross-origin calls from `localhost`, so the page can read both.

## MCP tools (`agent_mcp/`)

What the external agent sees. Five tools, short identifiers only, never a token.

| Tool | Arguments | Returns |
|---|---|---|
| `search_products` | `query`, `limit` | product cards, without prices |
| `request_quote` | `needs` (list of `product_id`, `amount`, `unit`), `delivery_date` | `checkout_id` and a readable summary of the quote |
| `authorize_checkout` | `checkout_id`, `request_text` (the human's original sentence) | `AuthorizationStatus` |
| `get_authorization_status` | `checkout_id` | `AuthorizationStatus` |
| `get_order` | `order_id` | `Order` without the receipt token |

## The `trust/` library (step A2)

Neither the gateway nor the harness calls the AP2 SDK directly. They call these functions:

```python
# trust/checkout.py
sign_checkout(checkout: AimoCheckout, merchant_key) -> str          # ES256 JWT
verify_checkout(checkout_jwt: str, merchant_jwks, now) -> AimoCheckout   # raises TrustError: bad signature or expired
checkout_hash(checkout_jwt: str) -> str

# trust/mandates.py
issue_open_mandates(policy: BuyerPolicy, manager_key, agent_public_jwk) -> OpenMandates
close_as_agent(open_mandates, agent_key, checkout_jwt: str) -> Authorization
close_as_human(manager_key, checkout_jwt: str) -> Authorization
verify_mandates(authorization: Authorization, checkout_jwt: str, manager_public_jwk) -> MandateCheck   # ok, signed_by, problems, reference

# trust/receipts.py
sign_receipt(order_id: str, reference: str, merchant_key) -> str
verify_receipt(receipt_jwt: str, merchant_jwks) -> dict
```

## Environment variables

| Name | Used by | Meaning |
|---|---|---|
| `VALIO_AIMO_API_KEY` | gateway, scripts | key for the Valio mock APIs |
| `GEMINI_API_KEY` | harness | key for Gemini Decision (AI Studio) |
| `VALIO_MODE` | gateway | `live` calls the Valio APIs, `replay` reads `contract/fixtures/valio/` |
| `AIMO_FROZEN_NOW` | both | an ISO time that replaces the clock in replay mode |
| `MERCHANT_URL` | harness, agent tools | default `http://localhost:8001` |
| `HARNESS_URL` | agent tools, surface | default `http://localhost:8002` |
| `AIMO_DATA_DIR` | gateway, scripts | where the three data files live, default `data/` |
