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
| `measured` | Valio counted or recorded it | stock of a `Stock` product, a price from the price API, an order cut-off, delivery reliability |
| `declared` | A supplier or data pool states it, or Valio promises it | country of origin and allergens from GS1 Synkka, the delivery date of an offer |
| `estimated` | Derived, not specific to this product | carbon footprint, an average of the product group |
| `unknown` | No data. `value` is `null` | stock of a `Terminal` product, a missing reliability figure |

| `source` | Where it comes from |
|---|---|
| `aimo_stock_count` | `/api/availability`, `logisticModel` = `Stock` |
| `supplier_warehouse` | `/api/availability`, `logisticModel` = `Terminal` (quantity unknown) |
| `aimo_availability_api` | `/api/availability`: the delivery date and the order cut-off of an offer |
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
| `OffersResponse` (a list of `Offer`) | `offers.act1.json` | gateway (`GET /offers`) | agent, surface |
| `QuoteRequest` | `quote-request.json` | agent | gateway |
| `AimoCheckout` (the signed quote) | `checkout.act1.json`, `.act2`, `.act3` | gateway (`POST /checkouts`) | harness, surface |
| `BuyerPolicy` | `policy.demo.json` | Colette writes it, the harness loads it | harness, surface |
| `Verdict` | `verdict.auto.json`, `.human.spend`, `.human.substitution`, `.deny` | harness | surface, audit |
| `ApprovalRequest` | `approval-request.pending.json` | harness | surface |
| `AuthorizationStatus` | `authorization-status.json` (six cases) | harness (`POST /authorize`) | agent, surface |
| `Authorization` (the mandates) | `authorization.json` | harness | gateway |
| `Order` | `order.json` | gateway | harness, agent, surface |
| `AuditEvent` | `audit-events.json` | both sides | surface |
| `DemoState` | `demo-state.idle.json`, `.normal-order`, `.substitution.pending`, `.substitution.approved`, `.attack` | demo driver (`GET /state`) | surface |

### The lookup

`GET /offers` is the brief's "product, price and availability lookup": what matches a query, at what price, and whether it can be ordered for a date. The example `offers.act1.json` is what the gateway really answers in replay mode to "1,000 litres of lactose-free milk by Monday". One `Offer` per product:

| Field | Meaning |
|---|---|
| `product` | the `ProductCard`, unchanged |
| `orderable`, `reason` | whether a quote for this request would get a line of this product. When it would not, `reason` says why: `late_delivery` (the order cut-off has passed), `out_of_stock` (Valio cannot deliver it, or its sales are blocked), `not_found` (Valio has no price or no availability for it), `unit_mismatch` (kilos asked for a product sold by the litre, or the other way round) |
| `price`, `comparison_price`, `comparison_unit` | claims, in cents and excluding tax: the price of one sales unit, and the price per litre or kilo (`comparison_unit` is `L` or `KG`) |
| `stock` | claim, in sales units, with the same rules as in a quote. An offer that is not orderable states no stock (`unknown`): `reason` says why |
| `available_date`, `closing_time` | claims: the day Valio would deliver, and the time until which the order must be in |
| `logistic_model` | `Stock` or `Terminal` |
| `to_order` | only when `amount` and `unit` are given and the offer is orderable: `quantity` in sales units (rounded up), `base_quantity` and `base_unit` (what those units hold), `total_minor`, `how` the size of one sales unit is known, and `stock_covers` |

`stock_covers` is `true` when Valio counted at least `quantity` units, `false` when it counted fewer (a quote would take what there is and propose substitutes for the rest), and `null` when Valio gives no count. In that last case the `stock` claim says which: "available, count not given" or unknown.

How the answer is built: the gateway searches the product file locally, keeps the 100 names closest to the query, and asks Valio for price and availability for those only, in one call to each API. `matched` says how many products the words found, `priced` how many were sent to Valio: when `matched` is larger, narrow the query. Offers are sorted: orderable first, then those whose counted stock covers the amount, then the cheapest per litre or kilo. `limit` (10 by default, 50 at most) cuts the list after sorting.

Search words, for this route and for `GET /products/search`: case, hyphens and punctuation do not count ("lactose-free" finds "lactose free"), Finnish letters do ("täysmaito" is not "taysmaito"), and a word may sit inside a longer one ("milk" finds "milkdrink"). Names with the query words as whole words come first, then the names with the fewest other words. Every category is returned, the card says which one: a search for "butter" also finds butter buns and peanut butter, so add a word to narrow it.

The answer is informative and not signed (`"binding": false`). Nothing in it commits Valio or the buyer, and a price can change until a quote is signed. To order, the agent asks `POST /checkouts` for the product it picked: the signed quote stays the only object a verdict, a mandate or a receipt can refer to. `GET /offers` answers HTTP 422 when the request has to change (an amount without its unit, a date replay mode has no answers for) and HTTP 503 when Valio's own API gives no usable answer.

### The signed quote

The quote is UCP's `Checkout` object as typed by the AP2 SDK (`ap2.sdk.generated.types.checkout.Checkout`): `id`, `merchant`, `status`, `currency`, `line_items`, `totals`, `links`, `expires_at`. We do not rename or remove any of those fields. Everything of ours sits under one extra top-level key, `aimo`, which the `Checkout` model allows. Per-line facts are in `aimo.lines`, keyed by the line item `id`.

The gateway signs the whole payload as an ES256 JWT. `checkout_hash` is the base64url SHA-256 of that JWT string. An approval, a mandate and a receipt all refer to the quote by this hash, so none of them can be reused for another cart.

A quote is valid until the order cut-off (`closing_time`), and at most 24 hours. That is the brief's "fixed prices": the price holds while a human takes the time to approve.

`POST /checkouts` answers HTTP 422 when the request cannot become a quote (unknown product, a unit the product does not have, a date replay mode has no answers for) and HTTP 503 when Valio's own API gives no usable answer: nothing is wrong with the request, it can be sent again. Both carry a readable `detail`.

Inside one quote, stock is counted once. Two needs for the same product, or two shortfalls covered by the same substitute, never add up to more than Valio has: the second one gets what the first one left, and a shortfall for the rest.

`aimo.shortfalls` says what could not be covered. `aimo.alternatives` ranks substitutes from Valio's own assortment, one per tier: `best` (same category, same allergens), `better` (same category, other allergens), `good` (a related category, plant-based drinks for milk drinks). The catalog already lists substitutes for some products (field `substitutions` in the product file, read both ways): they come first in a tier with `catalog_listed: true`. Then come the others (`catalog_listed: false`), the closest product name first, then the cheapest per litre or kilo. Closest means the most name words in common, pack sizes left out: the category alone is too wide, the cheapest "cheese" for a squeaky cheese was a cheddar cream. A substitute is only offered if it arrives on time, covers the whole shortfall, has complete allergen data and keeps every free-from promise of the original (a lactose-free product is only replaced by a lactose-free one). The `best` one is chosen unless `allow_alternatives` is false.

To pick another alternative, the agent asks for a new quote with `substitute_with` on the need, for example `{"product_id": "469363", "amount": 600, "unit": "L", "substitute_with": "464320"}`. The gateway refuses a product it would not offer.

A stock claim of a `Stock` product is `measured` with the count. The mock answers `9999999999` for most of them: the gateway turns that into `"value": "not_given"`, `certainty: "declared"` (Valio says it can deliver, without a count).

Each line carries its price per litre or kilo (`comparison_price_minor`, `comparison_unit`) as Valio's price API gives it. For the few products where it gives none (the caster sugar 460325), the gateway divides the price by the size of one sales unit in the product file. If the file has no size either, it is the price of one sales unit and `comparison_unit` is the sales unit.

A line that replaces another product says so in `substitute_for`, with the replaced product's id, name, brand, category, units, pack size, storage temperature, allergens, nutritional claims, labels and origin (`LineClaims` carries the same structured facts for the substitute line itself). Because the gateway signs all of them inside the quote, the harness and the judge compare the two without another lookup. For a line that is not a substitute, `substitute_for` is `null`.

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

### The order

`POST /checkouts/{id}/complete` takes the `Authorization` and checks, in this order: the quote exists, is still the one Valio signed and has not expired; the mandates verify against it (`trust.verify_mandates`); the quote has not been ordered yet.

| Case | Answer |
|---|---|
| Everything passes | HTTP 200 with the `Order`, status `accepted`, and a receipt signed by Valio. The receipt's `reference` is the order's `mandate_reference` |
| The same mandate is sent again | HTTP 200 with the same `Order`. A retry after a lost answer never orders twice |
| Another mandate for a quote that is already ordered | HTTP 403 |
| Expired quote, mandate for another quote or amount, agent mandate above the cap, wrong key | HTTP 403 |
| Unknown quote id | HTTP 404 |

A refusal is `{"problems": ["...", "..."]}`: every problem found, as readable sentences. Nothing is created on a refusal. Each of these cases writes a line in the gateway's audit log: `quote_issued`, `mandate_verified`, `order_accepted`, `order_replayed`, `order_refused`.

### The demo state

Everything the demo page shows, as one object. The demo driver builds it from the quote, the verdict, the approval, the order and both audit logs, and the page renders it without working out a fact itself. The five example files are real runs of the gateway and the harness in live mode on 14/11, for the customer `demo-restaurant-helsinki`.

| Field | Meaning |
|---|---|
| `scenarios` | the buttons: `id`, `title`, `hint` |
| `scenario` | the one on screen: `id`, `title`, `status`. After a reset `id` and `title` are `null` and `status` is `idle` |
| `kitchen` | the restaurant: `customer`, `name`, `covers_per_service`, `services`, `menu` (`course`, `dish`) |
| `request` | what the agent was asked: `text` (the sentence the harness receives), `delivery_date`, `lines` (`product_id`, `name`, `amount`, `unit`, `dish`), in the kitchen's units |
| `quote` | the `AimoCheckout`, without its token |
| `verdict`, `authorization`, `approval`, `order` | `Verdict`, `AuthorizationStatus`, `ApprovalRequest`, `Order`, each `null` until it exists |
| `attacks` | for the attack scenario: `key`, `title`, `status`, and the `problems` Valio answered |
| `steps` | the AP2 trail: always the seven steps below, in this order |
| `audit` | `buyer` and `merchant`: the lines each side wrote about this quote |

| `scenario.status` | Meaning |
|---|---|
| `idle` | nothing has run |
| `running` | the driver is between two calls |
| `waiting_for_human` | an approval is pending: the chef signs on the page |
| `done` | ordered, receipt signed |
| `refused` | no order: a `deny` verdict, a rejected or expired approval, or the attacks, all refused |

A step is `key`, `title`, `signer` (`manager`, `agent`, `merchant` or `none`), `status`, `detail` (one sentence to show), `proof` (a hash or an identifier, `null` when there is none) and `at`.

| `key` | Signer | `proof` |
|---|---|---|
| `open_mandate` | `manager` | hash of the open payment mandate |
| `signed_quote` | `merchant` | the quote hash (`checkout_hash`) |
| `verdict` | `none` | none: the rules are in `verdict` |
| `closed_mandates` | `agent` on `auto`, `manager` on `human`, `none` until the verdict says who | the mandate reference, the one the order and the receipt carry |
| `merchant_verifies` | `merchant` | none |
| `sandbox_payment` | `merchant` | the payment identifier |
| `signed_receipt` | `merchant` | hash of the receipt token |

| Step `status` | Meaning |
|---|---|
| `pending` | not reached yet |
| `done` | happened |
| `waiting` | waits for the human (only `closed_mandates`) |
| `refused` | Valio or the harness said no |
| `skipped` | will not happen in this scenario |

An attack's `status` is `pending`, `refused` (the expected end) or `accepted`, which would mean Valio let a bad mandate through: the page must show it as a failure.

The examples were recorded with the restaurant's policy (limit EUR 1,500) and the gateway's own pick of substitute, the bread cheese 475072 for the squeaky cheese 474880. One thing in them is ahead of the code: the `sandbox_payment` step is illustrative until the gateway books payments (step A9).

## Routes

Valio gateway, port 8001 (`merchant/`):

| Route | Input | Output |
|---|---|---|
| `GET /products/search?q=&limit=` | text query | `{"query", "count", "products": [ProductCard]}` |
| `GET /offers?q=&delivery_date=&amount=&unit=&limit=` | text query, delivery date, and optionally what is needed (`amount` with `unit`: `L`, `KG` or `ST`) | `OffersResponse`: `{"query", "delivery_date", "amount", "unit", "as_of", "binding": false, "matched", "priced", "count", "offers": [Offer]}`. Not signed |
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
| `GET /authorizations` | | `[AuthorizationStatus]` |
| `GET /authorizations/{checkout_id}` | | `AuthorizationStatus` |
| `GET /verdicts/{checkout_id}` | | `Verdict` |
| `GET /approvals?status=pending` | | `[ApprovalRequest]` |
| `GET /approvals/{id}` | | `ApprovalRequest` |
| `POST /approvals/{id}/decision` | `{"decision": "approve" or "reject", "decided_by"}` | `AuthorizationStatus` |
| `GET /policy` | | `BuyerPolicy` |
| `GET /audit` | | `[AuditEvent]` |
| `GET /` | | serves `surface/static` (and `/contract/examples` for `?mock=1`) |

Demo driver, port 8003 (`scenarios/run.py`):

| Route | Input | Output |
|---|---|---|
| `POST /scenarios/{id}/run` | | `DemoState` once the scenario has run: `done`, `waiting_for_human` or `refused` |
| `GET /state` | | `DemoState` |
| `POST /reset` | | `DemoState`, idle |

The driver plays the buying agent with the two calls of the MCP tools: `POST /checkouts` on the gateway, then `POST /authorize` on the harness. It holds no key. It only remembers which scenario is on screen and which quote it asked for: every `GET /state` reads the quote, the verdict, the approval, the order and both audit logs again from the two services. The scenarios it knows are in `state.scenarios`: `normal-order` and `substitution` today, the attack comes with step A10.

The chef's decision does not go through the driver: the page sends it to the harness (`POST /approvals/{id}/decision`), then reads `GET /state` again.

| Case | Answer |
|---|---|
| Unknown scenario | HTTP 404 |
| A scenario is still running | HTTP 409 |
| The gateway or the harness does not answer, or refuses the request | HTTP 502 with a readable `detail` that names the service. The state goes back to idle: nothing half-done is shown |

Two steps of the trail are not complete yet in the live state. `open_mandate` has no `proof`: the harness holds the open mandates and has no route that shows them. `sandbox_payment` is `skipped` with a sentence saying so, until the gateway books payments (step A9).

The three services allow cross-origin calls from `localhost`, so the page can read them all.

## MCP tools (`agent_mcp/`)

What the external agent sees. Six tools, short identifiers only, never a token. `lookup_offers` is in the contract since 14/11 and still has to be added to `agent_mcp/` (what to plug: `team/adrien/notes.md`).

| Tool | Arguments | Returns |
|---|---|---|
| `search_products` | `query`, `limit` | product cards, without prices |
| `lookup_offers` | `query`, `delivery_date`, optional `amount` with `unit`, `limit` | the offers of `GET /offers`: cards with price, stock, delivery date, cut-off, and orderable or not. Informative, not signed |
| `request_quote` | `needs` (list of `product_id`, `amount`, `unit`, optional `substitute_with`), `delivery_date` | `checkout_id` and a readable summary of the quote |
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
| `VALIO_MODE` | both | `live` calls the Valio APIs on the real clock. `replay` (the default) reads `contract/fixtures/valio/` and freezes the clock at the recording time (`frozen_now.txt` in that folder, 14/11 at 13:29). Give both services the same value |
| `AIMO_FROZEN_NOW` | both | optional: an ISO time with its offset that replaces the clock, in both modes |
| `MERCHANT_URL` | harness, agent tools | default `http://localhost:8001` |
| `HARNESS_URL` | agent tools, surface | default `http://localhost:8002` |
| `AIMO_DATA_DIR` | gateway, scripts | where the three data files live, default `data/` |
| `AIMO_STATE_DIR` | both | where quotes, orders, approvals and both audit logs are written, default `state/` |
