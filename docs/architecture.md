# Architecture, on one page

## The picture

```
BUYER SIDE (hotel chain)                                VALIO AIMO SIDE
Claude Desktop (external agent)
   │ MCP (6 tools, agent_mcp/)
   ├──────────────────────────────────────────────────▶ merchant/  FastAPI :8001
   │                                                     search, lookup, signed quote, order,
   ▼                                                     mandate verification, signed receipt, audit
harness/  FastAPI :8002 ──── HTTP: reads the quote ───▶      │
 verifies the signature, rules in code,   sends the mandate  ▼
 Gemini Decision judge, signs or not,                   real Valio APIs (price, availability)
 approval queue, audit                                  + 3 data files, live or replay mode
   ▲
surface/ (static page): the human approves and signs, audit logs from both sides
```

Two parties, as in real life. The buyer side holds the agent, the harness that guards it, and the page where a human approves. The Valio side holds the gateway. They only exchange signed pieces.

## One order, step by step

1. **Look up and compare.** The agent calls `lookup_offers` with the buyer's words, the delivery date and the amount ("lactose-free milk", Monday, 1,000 litres). The gateway searches the product file locally, then asks the real Valio APIs for price and availability, for a shortlist of 100 products at most and never for the whole catalog. It answers with offers: the product card (origin, allergens, labels, delivery reliability, carbon footprint), the price per unit and per litre or kilo, the stock, the delivery date and the order cut-off, each with its source and a certainty level, plus whether the product can be ordered and what the amount would cost. Orderable offers come first, cheapest first. This answer is not signed and commits nobody: it is there to compare. `search_products` still exists for a plain search by name, without prices.
2. **Quote.** The agent calls `request_quote` with the product it picked and an amount in litres or kilos. The gateway converts to sales units in code, asks the real Valio APIs for price and availability, and returns a quote it has signed. The agent gets a `checkout_id` and a readable summary.
3. **Authorize.** The agent calls `authorize_checkout` with the `checkout_id` and the human's original sentence. The harness fetches the signed quote itself, checks Valio's signature and the expiry, then runs the rules. For a substitution that is not pre-accepted, it asks the judge.
4. **Sign, or not.**
   - `auto`: the harness closes the mandates with the agent's key. This only works inside the limits the manager signed beforehand.
   - `human`: the harness creates an approval request. The page shows the exact quote and a countdown to the order cut-off. If the manager approves, the manager's key signs a mandate for this quote only.
   - `deny`: nothing is signed.
5. **Order.** The harness sends the mandates to the gateway. The gateway verifies the signatures, the merchant, the spend cap, the quote hash, single use and expiry. If all pass, it creates the order and returns a signed receipt. The harness verifies the receipt and tells the agent.

## Who signs what

| Piece | Signed by | Proves |
|---|---|---|
| Quote (UCP `Checkout` in a JWT) | Valio Aimo | Valio stated these prices, stock and facts, and nobody changed them |
| Open mandates (checkout and payment) | the manager, once | which merchant the agent may buy from, and up to how much |
| Closed mandate, verdict `auto` | the agent's key, held by the harness | this order, for this quote, inside the manager's limits |
| Closed mandate, verdict `human` | the manager, on the page | a person approved this exact quote |
| Receipt | Valio Aimo | Valio accepted the order that this mandate authorized |

The quote hash ties them together: mandate and receipt both refer to the hash of the signed quote, so none of them can be moved to another cart.

## How it maps to AP2

| AP2 role | Here |
|---|---|
| Shopping Agent | Claude Desktop, through MCP |
| Merchant | `merchant/`, the Valio Aimo gateway. Deterministic code, as AP2 requires for any verification |
| Trusted Surface (must be non-agentic) | `surface/`, the approval page |
| Agent Provider, holder of the agent key | `harness/` |
| Human not present | verdict `auto` |
| Human present | verdict `human` |

What AP2 leaves out and we add: AP2 says catalog APIs are outside its scope. For a wholesaler, that is where trust starts. Our contribution is the quote whose facts carry their source and certainty, and a guardrail model for food service (allergens, substitutions, cut-off deadlines).

What we do not claim: there is no official way to carry AP2 over MCP yet, so we cannot say "AP2 compliant". We use real AP2 mandates, built and verified with the official SDK.

## Why the agent cannot cheat

- It never holds a key and never sees a token, only identifiers.
- The rules run in the harness, not in the agent's prompt.
- If it skipped the harness and called the gateway directly, it would have no mandate, and the gateway would refuse.
- If the harness itself were compromised, it could still not sign above the cap: the cap is in the manager's signed mandate and the gateway checks it.
- The human approves on a page the agent cannot reach.
- The judge is a different model from the agent, and it can only make the verdict stricter.

## Sources

- AP2 v0.2: [specification](https://ap2-protocol.org/ap2/specification/), [Checkout mandate](https://ap2-protocol.org/ap2/checkout_mandate/), [repository and Python SDK](https://github.com/google-agentic-commerce/AP2/tree/main/code/sdk/python/ap2/sdk).
- Gemini Decisions API: [Google announcement, 11/11/2026](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/), [documentation](https://aistudio.google.com/docs/decisions-api), [rate limits](https://aistudio.google.com/docs/rate-limits).
- Valio Aimo brief and data: `contexte/challenge-1-valio-aimo.md`, `contexte/valio-aimo-resources.md`.
