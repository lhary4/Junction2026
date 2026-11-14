# Pitch Deck — Trusted Trade Agents for Valio Aimo

> **5-Slide Executive Deck (16:9 Landscape)**
> Exported companion PDF: `docs/pitch-deck.pdf`
> *Concept mock-up for Junction 2026 — uses challenge synthetic data.*

---

## Slide 1 — The Problem: Prompt Rules Cannot Guard Wholesale Food Trade

**Headline**: Kitchens want AI buying speed across 17,546 SKUs — without silent kitchen disasters.

- **Wholesale complexity at scale**: Professional kitchens convert recipes (`kg`, `L` across covers and services) into wholesale cartons, navigate supplier order cut-offs, and replace out-of-stock ingredients under tight prep deadlines.
- **Three failure modes of prompt-only buying agents**:
  1. **Pack-size hallucinations**: **94%** of the catalog (`16,440 / 17,546` items) is priced in pieces (`ST`), where pack counts sit inside product names (`100x2 cl` = 2 L, not 0.02 L). Prompt math misorders by 100x.
  2. **Dangerous silent substitutions & missing data**: **46%** of catalog products have **no allergen data** (`missing != free_from`). Naive category + lactose-free matching replaces fresh dessert squeaky cheese (`474880`) with **Nacho&Taco Cheddar cheese creme** (`474404`) or frozen blocks (`467148`).
  3. **Prompt rules are negotiable**: A rule inside an agent's system prompt can be talked around by marketing copy or prompt injection — and a bearer token cannot prove a chef authorized a specific cart.

**Bottom callout**: *In B2B food service, trust requires cryptographic proof of what Valio promised and who authorized the spend.*

---

## Slide 2 — The Idea: The Verdict Decides Who Signs

**Headline**: An external agent can search and quote freely — an order exists only with a valid AP2 mandate signature.

```
BUYER SIDE (50-Cover Kitchen)                         VALIO AIMO GATEWAY (:8001)
  Portal Driver or External ERP Agent (5 MCP Tools)
     │  short IDs only (never keys or JWTs)
     ├────────── lookup & quote ────────────────────▶ Converts units in code, ranks substitutes,
     ▼                                                attaches provenance/certainty claims,
  Buyer Harness (:8002)                               signs ES256 UCP Checkout quote (checkout_hash)
     ├─ Verifies Valio ES256 quote & expiry                  ▲
     ├─ Runs 9 deterministic policy rules (1–2 ms)           │
     ├─ Isolated judge (gemini-decision-1) on fuzzy subs     │
     └─ VERDICT DECIDES WHO SIGNS:                           │
         • AUTO  ──▶ Agent key closes manager's open mandate ┼─▶ Verifies ES256, EUR 1,500 cap,
         • HUMAN ──▶ Chef signs exact checkout_hash on page ─┘   checkout_hash & single use ->
         • DENY  ──▶ Nobody signs (Valio refuses unsigned)       Sandbox payment + ES256 Receipt
```

- **Zero agent authority over facts or keys**: Valio's gateway computes unit conversions and signs every product fact; the buying agent never touches a signing key or raw JWT.
- **Monotonic guardrails (`deny > human > auto`)**: Deterministic Python rules enforce signatures, expiry, blocked allergens (`AP`, `AN`), missing allergen data, delivery dates, and the **EUR 1,500** cap. `gemini-decision-1` only evaluates non-catalog substitutions and **can only make a verdict stricter**.

---

## Slide 3 — End-to-End Demo: 50-Cover Helsinki Kitchen on Live Valio Data

**Headline**: Three scenarios, one 7-step AP2 cryptographic trail, verified on 17,546 products.

- **Kitchen profile**: 50-cover Nordic November set menu across 3 dinner services (trout + horseradish smetana; sautéed reindeer + mash + lingonberries; warm `leipäjuusto` squeaky cheese + cloudberry jam) · **100% lactose-free dairy** · **no peanuts/tree nuts** · **EUR 1,500** autonomous cap.

| Scenario | Live Flow on Valio Catalog & APIs | Verdict & Cryptographic Outcome |
|---|---|---|
| **1. Normal Order** | 10 dairy & dry-goods lines with complete GS1 allergens, recipe `L`/`kg` converted in code (**~EUR 187 excl. VAT**) | **`auto`** — Agent key closes manager's open AP2 mandate -> Valio verifies -> **sandbox payment** -> ES256 receipt |
| **2. Substitution** | Fresh squeaky cheese `474880` past cut-off. `gemini-decision-1` rejects cheddar sauce `474404` (**1.4%**) & frozen `467148` (**1.0%**); routes chilled *Haapalan* `475072` (**91%** same use, **65%** preference fit) | **`human`** — Telegram alert (link only) -> chef inspects signed claims & clicks **Approve and sign** before cut-off -> manager-signed mandate -> **sandbox payment** -> receipt |
| **3. Attack** | Bypassed harness sends Valio: (1) over-cap agent mandate, (2) tampered quote, (3) replayed mandate | **`deny` (3x HTTP 403)** — Valio's gateway refuses all three in crimson; recorded in both SHA-256 audit logs |

- **Calibrated benchmark (`61` labelled substitution pairs)**: **0 / 50 false `auto` approvals** (100% `auto` precision), **17 / 17** bad substitutes caught below the `15%` floor, **~210 ms** median judge latency, **1–2 ms** deterministic rules + ES256 verification.

---

## Slide 4 — Open Standards + What We Add for Wholesale Food Trust

**Headline**: Standing on MCP, UCP, Google AP2, and ES256 — extended where B2B food service starts.

| Open Standard We Stand On | Role in Our Stack |
|---|---|
| **MCP (`mcp` 2.3)** | 5-tool door for external restaurant/hotel ERP agents alongside Valio's customer portal |
| **UCP `Checkout`** | Canonical shopping-cart quote payload (`line_items`, `totals` in minor units, `expires_at`) |
| **Google AP2 v0.2** | Open mandates (merchant + **EUR 1,500** `AmountRange` cap) & closed mandates (`checkout_hash` bound, verified by both sides) |
| **ES256 + OpenAPI** | Deterministic JWT signatures across manager, agent, and Valio keys; strict Pydantic schemas |

**Three wholesale trust additions (`checkout.aimo` + `harness/` + `common/audit.py`)**:
1. **Signed Provenance & Certainty Claims**: Every price, stock count, cut-off, origin, reliability figure, and group-average carbon footprint carries `{source, as_of, certainty}` (`measured` · `declared` · `estimated` · `unknown`). Unknown is never treated as safe.
2. **Isolated Calibrated Judge (`gemini-decision-1`)**: Reads **only** ES256-signed structured fields across all **29 GS1 allergen codes**, nutritional claims, labels, and storage temperatures — zero marketing text, zero agent prompt injection, fail-closed to `human`.
3. **Mutually Anchored SHA-256 Audit Logs**: Tamper-evident hash chains on both buyer and Valio sides, cross-anchored because each party stores the ES256 artifact signed by the other.

---

## Slide 5 — Path to Production: What Comes Next for Valio Aimo

**Headline**: Portal-first deployment today, open MCP & passkey cryptography tomorrow.

1. **Dual-Door Rollout (Valio Portal First + MCP Second)**
   - Embed the harness workflow directly inside Valio Aimo's existing web store, recipe, and inventory portal for independent kitchens (zero ERP required), while exposing the **5-tool MCP server** to hotel and restaurant chains with ERP agents — keeping unit math and substitute ranking on Valio's side.
2. **Browser WebAuthn Passkeys for `sign_human`**
   - Replace the demo's server-held manager key click with a hardware-backed **WebAuthn passkey** signature in the chef's browser using `checkout_hash` as the cryptographic challenge.
3. **Per-Customer Auth Tokens & Live Kitchen Sync**
   - Bind customer-specific catalog pricing and negotiated contracts via authenticated gateway tokens, and automate weekly draft reorders from portal inventory counts and reservation cover forecasts.
4. **Live AP2 Invoice & Payment Settlement**
   - Connect Step 6 from our simulated wholesale invoice **sandbox payment** to Valio Aimo's production ERP billing and AP2 Credential Provider / Payment Processor rails.

---

*Footer: Concept mock-up for Junction 2026 — uses challenge synthetic data.*
