# Léon's notes

Results, numbers and open questions for the others. Newest first.

## Signed substitution claims & typed `catalog_listed` flag in the quote (PR #25 follow-up to PR #21 & Adrien's PR #24)

Closed the last two contract cleanups (plus both `TECH-CHOICES.md` / `temperature_condition` notes from Adrien's PR #24) so 100% of substitution guardrail & judge inputs come from the ES256-signed quote with zero unsigned `/products/search` lookup and zero string matching on `Alternative.why`:
- **`contract/models.py` + `merchant/quotes.py` + `contract/schemas/`**:
  - Added optional defaulted fields on `LineClaims` (`brand`, `size_per_sales_unit`, `temperature_condition`, `nutritional_claims`) and `SubstituteFor` (`brand`, `sales_unit`, `base_unit`, `size_per_sales_unit`, `temperature_condition`, `nutritional_claims`, `labels`, `origin`), plus `catalog_listed: bool = False` on `Alternative`. All existing recorded JWTs and example JSONs stay 100% valid because every new field has a safe default.
- **`harness/app.py` + `harness/rules.py` + `harness/judge.py`**:
  - Removed `_fetch_product_cards` (`GET /products/search`) from `harness/app.py`—every fact passed to `evaluate()` and `gemini-decision-1` (including `temperature_condition`) now comes strictly from the verified `checkout_jwt`.
  - `_is_pre_accepted` now checks `chosen_alt.catalog_listed` directly instead of matching `"listed as a substitute in the catalog"` in `chosen_alt.why`.
  - Corrected `"15-minute expiry"` -> `"24-hour expiry"` in `TECH-CHOICES.md`.

## Harness hardening against the real gateway, real fixtures & 61 substitution pairs (answers to Adrien's PR #18 & PR #19 notes)

Thanks Adrien for the thorough read in PR #18 and PR #19! Addressed all four items plus several extra edge cases we found while playing through `contract/fixtures/valio/` (157 products), `scenarios/policy.demo.json`, `scenarios/pairs.csv` (30 milk pairs), and `scenarios/pairs.families.csv` (31 cross-family pairs):

1. **Pre-acceptance (`_is_pre_accepted` in `harness/rules.py`) — coffee milk `463380` & vanilla milk `473142` now hit Gemini Decision instead of flying through:**
   - Even with `"pre_accepted": "same_category_and_same_allergens"` in `scenarios/policy.demo.json`, pre-acceptance now ONLY triggers when **(a)** the agent did not force an explicit `substitute_with`, **(b)** the chosen `best` candidate in `checkout.aimo.alternatives` is explicitly `"listed as a substitute in the catalog"` (never a cheapest-in-category fallback), and **(c)** no origin, quality label, non-lactose `free_from` allergen, or key dietary/plainness claim (`FREE_FROM_LACTOSE`, `ORGANIC`, `UNSWEETENED`, etc.) is lost.
   - **Important Act 3 finding for Adrien & Colette (`469363 -> 464306` vs `464201`):** In replay mode, `469363` is **UHT** (`temp=8°C`) while Valio's default listed substitute `464306` is **chilled** (`temp=4°C`). Under `scenarios/policy.demo.json` (*"Colder storage needed: a UHT or shelf-stable product replaced by a chilled one -> A HUMAN DECIDES"*), if `"pre_accepted"` were changed to `"none"`, `gemini-decision-1` scores `469363 -> 464306` at **`0.614` (`human`)** because of the UHT -> chilled storage change! Keeping `"pre_accepted": "same_category_and_same_allergens"` tightened to catalog-listed `best` substitutes without `substitute_with` solves both at once: Act 3's default `469363 -> 464306` stays `auto` (trusted Valio catalog substitute), while `463380` (Arla Cafè milk -> **`0.168`, `human`**), `473142` (sweetened vanilla coffee milk -> **`0.068`, `deny`/`human`**), `460509` (non-organic soya -> **`0.044`, `deny`/`human`**), and `464201` (Valio UHT lactose-free Finnish milk -> **`0.943`, `auto`**) all go through `gemini-decision-1`.
2. **Product cards passed to the judge (`harness/app.py`, `harness/rules.py`, `harness/judge.py`):**
   - `harness/app.py` now enriches substitution products via `GET /products/search?q={name}&limit=20` on the gateway before calling `evaluate()`, recovering `nutritional_claims` (e.g. `FREE_FROM_LACTOSE`), `brand`, `sales_unit`, `base_unit`, and `size_per_sales_unit` — verified to match **157/157** products in `contract/fixtures/valio/products.json` without needing a breaking `contract/` change!
   - `_build_original_card` also merges signed `origin` and `labels` from the original product's partial-stock line (such as `li-1` in Act 3), and signed quote facts always take precedence over catalog search fields.
   - `harness/judge.py` now maps all **29 standard GS1 Synkka allergen codes** (not just 6), includes allergen `data_status`, and passes `origin_country`, `labels`, `nutritional_claims`, and pack/unit sizes while still stripping marketing copy, prices, and untrusted `request_text` (tested live: keeping `request_text` out keeps agent prompt-injection influence at **0%**).
   - That directly solved the `469363 -> 464201` mystery: `464201` declares lactose-free via `nutritional_claims: ["FREE_FROM_LACTOSE"]` (with `free_from: []`) and Finnish origin via `origin: "FI"` + `labels: ["GOODS_FROM_FINLAND_BLUE_SWAN"]`. Passing those structured fields lifted `469363 -> 464201` from `0.069` back to **`0.943` (`auto`)**.
3. **Live 61-pair benchmark on `gemini-decision-1` (`scenarios/pairs.csv` + `scenarios/pairs.families.csv`):**
   - **0 false `auto`s across all 50 `ask` + `no` pairs (100% precision on `auto`)**: every single `ask` pair (33/33) scored `< 0.85` (`0.017`–`0.799`), and the one `0.799` pair also has missing allergen data caught by `allergen-data-known`.
   - **17/17 `no` pairs (100%)** scored `<= 0.133` (`0.010`–`0.133`), all cleanly below `judge_floor = 0.15`.
   - Conclusion for Colette: `judge_auto_threshold = 0.85` and `judge_floor = 0.15` in `scenarios/policy.demo.json` work cleanly as-is!
4. **Approval deadline vs quote expiry (`harness/rules.py`):**
   - Approval `deadline` now uses `min(checkout.expires_at, checkout.aimo.closing_time)` instead of `closing_time` alone, so in replay mode (`expires_at = 13:29:07` vs `closing_time = 17:00` next day) a pending card never claims to stay open after the quote itself has expired.
5. **Gateway errors & lost `/complete` retry safety (`harness/app.py`, `harness/approvals.py`):**
   - Unreachable gateway / timeout / invalid JSON now returns a clean **HTTP 502** with a readable detail instead of an unhandled 500, and a malformed outer `checkout` payload fails closed as `deny` (`quote-signature`).
   - `ApprovalStore` now persists `signed_mandates.json` before `POST /checkouts/{id}/complete` so if a network drop loses Valio's 200 response, retrying `/authorize` or `/decision` replays the **exact same** `Authorization` and hits `merchant/orders.py`'s idempotent fast path instead of getting refused with HTTP 403.
   - Removed hardcoded `"Valio Aimo"` / `"valio-aimo"` strings in `harness/app.py` in favor of `checkout.merchant.name` / `checkout.merchant.id`.
6. **Multi-substitution quotes, uncovered shortfalls & policy expiry (`harness/rules.py`):**
   - Rules now inspect **every** substitute line in multi-item quotes (not just `sub_lines[0]`), escalate uncovered shortfalls (`checkout.aimo.shortfalls` with `allow_alternatives=False`) to `human` instead of auto-ordering a partial delivery, and route expired buyer policies (`now >= policy.valid_until`) to `human`.
7. **Shared per-file lock in `common/audit.py` (PR #18 follow-up):**
   - `common/audit.py` now keeps a module-level lock registry keyed by `path.resolve()`, so separate `AuditLog(path)` instances across concurrent web threads serialize cleanly on the same file. Adrien can drop `_LOCK` in `merchant/audit.py` whenever convenient.

## L4: Harness service (`harness/app.py`, `harness/signer.py`, `harness/approvals.py`)

- L1 + L2 + L3 + L4 are united and tested together with `main` (`uv run python scripts/dev.py` now starts both Valio's gateway on `:8001` and the buyer's harness on `:8002` with one command).
- All contract routes on `:8002` are live and tested against both a fake gateway and Adrien's real `merchant.app` (`VALIO_MODE=replay`):
  - `POST /authorize`, `GET /authorizations/{checkout_id}`, `GET /approvals?status=pending`, `POST /approvals/{id}/decision`, `GET /policy`, `GET /audit`, plus `surface/static` served at `/` (and `/contract/examples` mounted so `?mock=1` also works on `:8002`).
  - Extra read-only routes for Colette's C4 live surface (also listed in `docs/contract.md`): `GET /authorizations`, `GET /verdicts/{checkout_id}`, and `GET /approvals/{approval_id}`.
- Replay clock compatibility confirmed with Adrien's PR #15 (`common/clock.py` frozen at `2026-11-14T13:29:15+02:00` in `VALIO_MODE=replay`, overridable via `AIMO_FROZEN_NOW` to demo expiry).
- Pending approvals automatically transition to `expired` once `clock.now() >= deadline`, both when polled and if someone tries to decide after cut-off; deciding an already approved/rejected request returns HTTP 409.
- Pitch note on `sign_human`: in the demo the Approve button on `:8002` triggers the buyer-side manager key; in production this step is a WebAuthn passkey signature in the browser on the approval surface.

## L2 & L3: Shared audit log (`common/audit.py`) and rules (`harness/rules.py`)

- `common/audit.py` (`AuditLog(path)` with `append`, `read`, `verify`, `digest`, `default_log_path`) uses the exact same canonical JSON SHA-256 formula as `merchant/audit.py`, so Adrien can swap `merchant/audit.py` to `AuditLog(default_log_path("merchant"))` whenever `feat/audit-log` is merged.
- `harness/rules.py` reproduces all four `contract/examples/verdict.*.json` files with exact equality.

## L1: Gemini Decision on the substitution case

Model: `gemini-decision-1` (`v1beta`), original `469363` (*Arla Semi skimmed milkdrink 1 L UHT lactose free Suomesta*), `auto_threshold = 0.85`, `floor = 0.15`.

| Candidate | `within_preferences` | `same_use` | Routing (`within_preferences` / `same_use`) |
|---|---|---|---|
| 464201 Valio semi skimmed UHT lactose free | **0.9645** (conf 0.9645) | **0.9772** (conf 0.9772) | `auto` / `auto` |
| 463380 Arla Cafè milk UHT lactose free | **0.2272** (conf 0.7728) | **0.4815** (conf 0.5185) | `human` / `human` |
| 464320 Oatly iKaffe oat drink | **0.0190** (conf 0.9810) | **0.0892** (conf 0.9108) | `human` / `human` |

Order check (`464201 > 463380 > 464320`): passed on both `within_preferences` (`0.9645 > 0.2272 > 0.0190`) and `same_use` (`0.9772 > 0.4815 > 0.0892`) on the first phrasing.

Median latency over 10 calls: **245.4 ms** (min **189.9 ms**, max **487.9 ms**; two `noul` questions evaluated in parallel per call).

What happens without a key or on a timeout:
- Missing `GEMINI_API_KEY`: skips network call and immediately returns two `JudgeAnswer`-shaped dicts with `routed: "human"`, `probability: null`, `confidence: null`.
- Timeout (default 5.0 s, verified live with a 1 ms deadline) or any SDK/HTTP error: catches the exception and fails closed with `routed: "human"`, `probability: null`, `confidence: null`.
