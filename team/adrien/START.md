# Adrien: contract, signing library, Valio gateway

Read `PLAN.md` first, then `docs/contract.md`. You are on the critical path: A1 and A2 unblock the two other lanes, so they come before everything else.

## What you own

- `contract/`, `trust/`, `common/clock.py`, `pyproject.toml`, `uv.lock`, `scripts/`, `merchant/`, `tests/test_contract.py`, `tests/test_trust.py`, `tests/test_merchant_*.py`.
- Do not edit `harness/`, `common/audit.py`, `surface/`, `agent_mcp/`, `scenarios/` (one exception in A3, announced).

## Rules for every step

- One step = one branch = one small PR. Start from an up-to-date `main`.
- Before the PR: `uv sync`, `uv run pytest`, `uv run ruff check`. Report failures as they are.
- `TECH-CHOICES.md` already covers the choices below. Write "Tech choices: no change" in the PR unless you add a new one.
- All code, comments and commit messages in English.

## A1. The contract as Pydantic models (13:15 to 14:05)

Branch `feat/contract-models`. Goal: the JSON files in `contract/examples/` become models that everyone imports.

1. `pyproject.toml` and `.python-version` (3.14). Not a package: `[tool.uv] package = false`, and `[tool.pytest.ini_options] pythonpath = ["."]` so the top-level folders import each other. Pin what was proven:
   - `ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56db72a6385bce3e5c1112b3a56ce60acb43`
   - `pydantic==2.12.5`, `fastapi==0.162.7`, `uvicorn==0.54.0`, `mcp==2.3.0`, `google-genai==3.3.0`, `requests`
   - dev: `pytest`, `ruff`
2. `contract/ap2.py`: re-export from the SDK `Checkout`, `LineItem`, `Item`, `Total`, `Link`, `Merchant`, `OpenCheckoutMandate`, `AllowedMerchants`, `CheckoutMandate`, `OpenPaymentMandate`, `AmountRange`, `PaymentMandate`, `Amount`, `PaymentInstrument`. Import paths are in `spikes/stack/core.py`.
3. `contract/models.py`: `Claim`, `AllergenInfo`, `ProductCard`, `QuoteRequest`, `LineClaims`, `AimoExtension`, `AimoCheckout(Checkout)`, `BuyerPolicy`, `RuleResult`, `JudgeAnswer`, `Verdict`, `ApprovalRequest`, `AuthorizationStatus`, `Authorization`, `Order`, `AuditEvent`. Enums as `Literal` types. Field names exactly as in the examples.
4. `scripts/export_schemas.py` writes `contract/schemas/*.json` from the models.
5. `tests/test_contract.py`: every example file validates with its model. The three `checkout.act*.json` validate with both the SDK's `Checkout` and our `AimoCheckout`, and `aimo.lines` keys match the line item ids.

If an example has to change to fit the SDK, change it in the same PR and say so at the 14:05 sync.

Done when: the three commands pass and the PR is merged by 14:05.

## A2. The `trust/` library (14:05 to 14:45)

Branch `feat/trust-library`. Goal: the gateway and the harness sign and verify through a handful of functions and never touch the SDK. Signatures are in `docs/contract.md`. Lift the code from `spikes/stack/core.py`, and the cases from `spikes/ap2/`.

1. `trust/keys.py`: three ES256 keys (`manager`, `agent`, `merchant`) as JWK files. Demo keys are committed under `contract/fixtures/keys/` with a `README.md` saying "DEMO ONLY, protect nothing real". `public_jwks()` for the gateway's JWKS route.
2. `trust/checkout.py`, `trust/mandates.py`, `trust/receipts.py`. In the mandates: `aud` is the merchant id, `nonce` is the checkout id, the payment mandate's `transaction_id` is the checkout hash, the spend cap comes from `policy.autonomous_limit_minor` as `AmountRange`.
3. `common/clock.py`: `now()` returns the current time, or `AIMO_FROZEN_NOW` when set.
4. `tests/test_trust.py`: the 13 cases, the human-signed mandate (accepted with the manager's key, refused with the agent's), a receipt round trip.
5. `scripts/make_fixtures.py` writes `contract/fixtures/checkout.valid.jwt`, `checkout.tampered.jwt`, `checkout.expired.jwt` and `open_mandates.json`, built from `contract/examples/checkout.act1.json`.

Done when: tests pass, PR merged by 14:45, and you have told Léon the fixtures are there.

## A3. Data files and recorded fixtures (14:45 to 15:25)

Branch `feat/data-and-fixtures`. Goal: replay mode has real answers, recorded while the Monday cut-off is still open.

1. `scripts/fetch_data.py`: downloads the product file, the delivery reliability file and the carbon footprint file into `AIMO_DATA_DIR` (default `data/`, ignored by git), and skips what is already there. On your Mac the three files may already be in `~/junction-2026/data/`. The API answers HTTP 403 to Python's default `urllib` user agent: use `requests`.
2. `scripts/record_fixtures.py` for delivery date 2026-11-16: the lactose-free milks (category 10400), the plant-based drinks (category 10402) and every product listed in the `substitutions` field of the five demo products. It writes `contract/fixtures/valio/`: the product records, their price and availability answers, their reliability and carbon rows, and `frozen_now.txt`. Keep the folder under 1 MB.
3. Check the demo against the recorded answers: 464306 must be a `Stock` product with at least 2,000 units and a cut-off on Sunday 17:00, and 469363 must have less stock than 600. If not, pick other products now and tell everyone, because the demo script depends on them.
4. `scenarios/pairs.todo.csv` for Colette (the one file you create in her folder, say it out loud): 30 rows, columns `original_id`, `original_name`, `candidate_id`, `candidate_name`, `candidate_contains`, `same_category`, `label` (empty).

Done when: PR merged by 15:25 and Colette knows the pairs file is there.

## A4. Gateway, part 1: search and signed quotes (15:25 to 16:10)

Branch `feat/merchant-search-quote`. Reuse `v1.py` (your local branch `feat/tiny-v1`): `api()`, `names()`, `size_per_sales_unit()`, `delivery_problem()`, the search by majority category, the split across two products. Drop its cap of 20 products, the API accepts 1,000.

1. `merchant/catalog.py`: load the products (full file in live mode, fixture subset in replay), join reliability and carbon, build `ProductCard`. Allergens come from the classifications `allergen` (`CONTAINS`) and `nonAllergen` (`FREE_FROM`); both empty means `data: "missing"`. Leave `coolTemperature` and `warmTemperature` out of the labels.
2. `merchant/units.py`: litres or kilos to sales units, rounded up, with the explanation string.
3. `merchant/valio_client.py`: `live` or `replay` from `VALIO_MODE`.
4. `merchant/quotes.py`: a `QuoteRequest` becomes an `AimoCheckout`. Stock of a `Stock` product is `measured`; a `Terminal` product is `unknown` with a `null` value. Partial stock gives a split, a shortfall and ranked alternatives: the catalog's own `substitutions` first, then the same category. `expires_at` is the cut-off, at most 24 hours ahead. Signed with `trust.sign_checkout`.
5. `merchant/app.py`: `GET /products/search`, `POST /checkouts`, `GET /checkouts/{id}`, `GET /.well-known/jwks.json`, cross-origin calls allowed from `localhost`.

Done when: a search returns cards with reliability and carbon, and a quote for act 1 comes back as a token that `trust.verify_checkout` accepts, in both modes.

## A5. Gateway, part 2: orders (16:10 to 16:55)

Branch `feat/merchant-orders`.

1. `POST /checkouts/{id}/complete` takes an `Authorization`. Checks, in this order: the quote exists and has not expired, `trust.verify_mandates` passes, the mandate reference has not been used. The same mandate sent twice returns the same order. Another mandate for an already ordered quote is refused. A refusal is HTTP 403 with the list of problems.
2. On success: an `Order` with status `accepted` and a receipt from `trust.sign_receipt`.
3. `GET /orders/{id}` and `GET /audit`, using `common/audit.py` (Léon's, merged around 14:35).
4. `scripts/dev.py`: starts the gateway on 8001 and the harness on 8002, on any operating system.
5. Tests: a valid agent mandate gives an order whose receipt verifies, a tampered quote is refused, an agent mandate above the cap is refused, a human-signed mandate is accepted, a replay returns the same order.

At 16:30, stop for five minutes with Léon: his harness must fetch and verify one of your quotes.

## 17:00 checkpoint

With Léon and Colette, write `scenarios/run.py` on one screen: act 1 through the real gateway and the real harness in replay mode. Expected: verdict `auto`, an order with its receipt, matching lines in both logs.

## After 17:00

In order: live mode for all four acts, the substitute ranking for act 3, then whatever the cut list in `PLAN.md` still allows. Milestones are in `PLAN.md`.
